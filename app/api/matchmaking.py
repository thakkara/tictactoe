"""
Matchmaking API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_db
from app.services.matchmaking_service import matchmaking_service, MatchmakingPreferences
from app.services.lobby_manager import lobby_manager
from app.services.skill_calculator import skill_calculator
from app.models.matchmaking import PlayerQueue, MatchmakingStatus, PlayerRating
from app.schemas.matchmaking import (
    MatchmakingRequest, MatchmakingResponse, QueueStatusResponse,
    PlayerRatingResponse, MatchHistoryResponse
)

router = APIRouter(
    prefix="/matchmaking",
    tags=["matchmaking"],
    responses={404: {"description": "Not found"}}
)


@router.post("/join", response_model=MatchmakingResponse)
async def join_matchmaking(
    request: MatchmakingRequest,
    db: Session = Depends(get_db)
):
    """
    Join the matchmaking queue.
    
    Player will be automatically matched with suitable opponents based on:
    - Skill rating (ELO)
    - Grid size preferences  
    - Queue type (ranked/casual)
    - Maximum wait time tolerance
    """
    try:
        preferences = MatchmakingPreferences(
            grid_sizes=request.grid_sizes,
            max_rating_difference=request.max_rating_difference,
            preferred_queue_type=request.queue_type,
            max_wait_time=request.max_wait_time
        )
        
        queue_entry = await matchmaking_service.join_matchmaking(
            db, request.player_id, preferences
        )
        
        # Update lobby status
        await lobby_manager.update_player_status(
            request.player_id, 
            "searching",
            preferences.__dict__
        )
        
        return MatchmakingResponse(
            success=True,
            queue_id=queue_entry.id,
            estimated_wait_time=30,  # Initial estimate
            message=f"Searching for opponents with rating ±{request.max_rating_difference}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to join matchmaking: {str(e)}")


@router.post("/leave")
async def leave_matchmaking(
    player_id: int,
    db: Session = Depends(get_db)
):
    """Leave the matchmaking queue"""
    
    try:
        success = await matchmaking_service.leave_matchmaking(db, player_id)
        
        if success:
            # Update lobby status
            await lobby_manager.update_player_status(player_id, "idle")
            
            return {"success": True, "message": "Left matchmaking queue"}
        else:
            return {"success": False, "message": "Player was not in queue"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to leave matchmaking: {str(e)}")


@router.get("/status", response_model=QueueStatusResponse)
def get_queue_status(db: Session = Depends(get_db)):
    """Get current matchmaking queue statistics"""
    
    status = matchmaking_service.get_queue_status(db)
    
    return QueueStatusResponse(
        total_searching=status["total_searching"],
        queue_breakdown=status["queue_breakdown"],
        active_searches=status["active_searches"]
    )


@router.get("/player/{player_id}/rating", response_model=PlayerRatingResponse)
def get_player_rating(player_id: int, db: Session = Depends(get_db)):
    """Get a player's current ratings and statistics"""
    
    rating = db.query(PlayerRating).filter(
        PlayerRating.player_id == player_id
    ).first()
    
    if not rating:
        # Create default rating for new player
        rating = PlayerRating(player_id=player_id)
        db.add(rating)
        db.commit()
    
    return PlayerRatingResponse(
        player_id=player_id,
        overall_rating=rating.overall_rating,
        grid_3x3_rating=rating.grid_3x3_rating,
        grid_4x4_rating=rating.grid_4x4_rating,
        grid_5x5_rating=rating.grid_5x5_rating,
        games_played=rating.games_played,
        rating_deviation=rating.rating_deviation,
        peak_rating=rating.peak_rating,
        current_win_streak=rating.current_win_streak,
        current_loss_streak=rating.current_loss_streak,
        best_win_streak=rating.best_win_streak
    )


@router.get("/player/{player_id}/history", response_model=List[MatchHistoryResponse])
def get_match_history(
    player_id: int, 
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get a player's recent match history"""
    
    from app.models.matchmaking import MatchmakingHistory
    
    history = db.query(MatchmakingHistory).filter(
        or_(
            MatchmakingHistory.player1_id == player_id,
            MatchmakingHistory.player2_id == player_id
        )
    ).order_by(MatchmakingHistory.created_at.desc()).limit(limit).all()
    
    return [
        MatchHistoryResponse(
            match_id=h.id,
            opponent_id=h.player2_id if h.player1_id == player_id else h.player1_id,
            game_id=h.game_id,
            rating_difference=h.rating_difference,
            wait_time=h.wait_time_player1 if h.player1_id == player_id else h.wait_time_player2,
            match_quality_score=h.preference_match_score,
            game_completion_status=h.game_completion_status,
            created_at=h.created_at
        )
        for h in history
    ]


@router.post("/predict")
def predict_match_outcome(
    player1_id: int,
    player2_id: int,
    db: Session = Depends(get_db)
):
    """Predict the outcome of a potential match between two players"""
    
    rating1 = db.query(PlayerRating).filter(PlayerRating.player_id == player1_id).first()
    rating2 = db.query(PlayerRating).filter(PlayerRating.player_id == player2_id).first()
    
    if not rating1 or not rating2:
        raise HTTPException(status_code=404, detail="Player rating not found")
    
    prediction = skill_calculator.predict_match_outcome(
        rating1.overall_rating,
        rating2.overall_rating
    )
    
    match_quality = skill_calculator.calculate_match_quality(
        rating1.overall_rating,
        rating2.overall_rating,
        rating1.rating_deviation,
        rating2.rating_deviation
    )
    
    return {
        "prediction": prediction,
        "match_quality": match_quality,
        "rating_difference": abs(rating1.overall_rating - rating2.overall_rating)
    }


# WebSocket endpoints for real-time lobby
@router.websocket("/lobby")
async def lobby_websocket(websocket: WebSocket, player_id: int, db: Session = Depends(get_db)):
    """Real-time lobby connection for matchmaking updates"""
    
    success = await lobby_manager.connect_player(websocket, player_id, db)
    if not success:
        return
    
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await lobby_manager.handle_websocket_message(player_id, message, db)
            except json.JSONDecodeError:
                await lobby_manager._send_to_player(player_id, {
                    "type": "error",
                    "message": "Invalid JSON message"
                })
                
    except WebSocketDisconnect:
        await lobby_manager.disconnect_player(player_id)


@router.websocket("/queue/{player_id}")
async def queue_updates_websocket(websocket: WebSocket, player_id: int):
    """Real-time updates for players in matchmaking queue"""
    
    await websocket.accept()
    
    try:
        while True:
            # Send periodic queue updates
            queue_entry = db.query(PlayerQueue).filter(
                PlayerQueue.player_id == player_id,
                PlayerQueue.status == MatchmakingStatus.SEARCHING
            ).first()
            
            if queue_entry:
                wait_time = (datetime.utcnow() - queue_entry.joined_at).total_seconds()
                await websocket.send_text(json.dumps({
                    "type": "queue_update",
                    "wait_time": int(wait_time),
                    "current_rating_range": queue_entry.current_rating_range,
                    "status": queue_entry.status
                }))
            else:
                # Player no longer in queue
                await websocket.send_text(json.dumps({
                    "type": "queue_left",
                    "reason": "No longer in queue"
                }))
                break
            
            await asyncio.sleep(5)  # Update every 5 seconds
            
    except WebSocketDisconnect:
        pass


# Background task integration
@router.on_event("startup")
async def setup_matchmaking_background_tasks():
    """Setup background tasks for matchmaking"""
    
    # Background task to clean up expired queue entries
    async def cleanup_expired_queues():
        while True:
            try:
                with get_db() as db:
                    expired_entries = db.query(PlayerQueue).filter(
                        PlayerQueue.status == MatchmakingStatus.SEARCHING,
                        PlayerQueue.joined_at < datetime.utcnow() - timedelta(minutes=10)
                    ).all()
                    
                    for entry in expired_entries:
                        entry.status = MatchmakingStatus.TIMEOUT
                        await lobby_manager.update_player_status(entry.player_id, "idle")
                    
                    if expired_entries:
                        db.commit()
                        logger.info(f"Cleaned up {len(expired_entries)} expired queue entries")
                
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                logger.error(f"Error in queue cleanup: {e}")
                await asyncio.sleep(60)
    
    # Start background task
    asyncio.create_task(cleanup_expired_queues())