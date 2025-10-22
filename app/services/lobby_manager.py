"""
Real-time lobby management with WebSocket support.
"""
import json
import asyncio
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models.matchmaking import PlayerQueue, MatchmakingStatus
from app.models.player import Player
from app.services.matchmaking_service import MatchmakingPreferences

logger = logging.getLogger(__name__)


@dataclass
class LobbyPlayer:
    """Player information for lobby display"""
    player_id: int
    username: str
    rating: int
    status: str  # "idle", "searching", "in_game"
    preferences: Optional[Dict] = None
    connected_at: datetime = None
    
    def to_dict(self) -> Dict:
        return {
            "player_id": self.player_id,
            "username": self.username,
            "rating": self.rating,
            "status": self.status,
            "preferences": self.preferences,
            "connected_since": self.connected_at.isoformat() if self.connected_at else None
        }


@dataclass
class LobbyStats:
    """Current lobby statistics"""
    total_players: int
    searching_players: int
    avg_wait_time: float
    queue_breakdown: Dict[str, int]
    recent_matches: int
    
    def to_dict(self) -> Dict:
        return asdict(self)


class LobbyConnectionManager:
    """Manage WebSocket connections for the game lobby"""
    
    def __init__(self):
        # Active WebSocket connections
        self.active_connections: Dict[int, WebSocket] = {}  # player_id -> websocket
        self.connection_metadata: Dict[int, LobbyPlayer] = {}  # player_id -> player_info
        
        # Lobby state
        self.lobby_players: Dict[int, LobbyPlayer] = {}
        self.matchmaking_queue_cache: Dict[str, List[Dict]] = {}
        
        # Background tasks
        self.update_task: Optional[asyncio.Task] = None
        self.stats_update_interval = 5  # seconds
    
    async def connect_player(self, websocket: WebSocket, player_id: int, db: Session):
        """Connect a player to the lobby"""
        
        await websocket.accept()
        
        # Get player info from database
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            await websocket.close(code=4004, reason="Player not found")
            return False
        
        # Store connection
        self.active_connections[player_id] = websocket
        
        # Create lobby player object
        lobby_player = LobbyPlayer(
            player_id=player_id,
            username=player.username,
            rating=getattr(player, 'overall_rating', 1200),  # From rating relationship
            status="idle",
            connected_at=datetime.utcnow()
        )
        
        self.connection_metadata[player_id] = lobby_player
        self.lobby_players[player_id] = lobby_player
        
        # Send initial lobby state to new player
        await self._send_initial_lobby_state(websocket, db)
        
        # Broadcast player joined to all other players
        await self._broadcast_player_update(lobby_player, "joined")
        
        # Start background update task if not running
        if not self.update_task or self.update_task.done():
            self.update_task = asyncio.create_task(self._periodic_updates(db))
        
        logger.info(f"Player {player_id} ({player.username}) connected to lobby")
        return True
    
    async def disconnect_player(self, player_id: int):
        """Disconnect a player from the lobby"""
        
        if player_id in self.active_connections:
            del self.active_connections[player_id]
        
        if player_id in self.lobby_players:
            lobby_player = self.lobby_players[player_id]
            del self.lobby_players[player_id]
            
            # Broadcast player left
            await self._broadcast_player_update(lobby_player, "left")
        
        if player_id in self.connection_metadata:
            del self.connection_metadata[player_id]
        
        logger.info(f"Player {player_id} disconnected from lobby")
    
    async def update_player_status(self, player_id: int, status: str, preferences: Dict = None):
        """Update a player's status in the lobby"""
        
        if player_id in self.lobby_players:
            self.lobby_players[player_id].status = status
            if preferences:
                self.lobby_players[player_id].preferences = preferences
            
            await self._broadcast_player_update(self.lobby_players[player_id], "updated")
    
    async def handle_websocket_message(self, player_id: int, message: Dict, db: Session):
        """Handle incoming WebSocket messages from players"""
        
        message_type = message.get("type")
        
        if message_type == "ping":
            await self._send_to_player(player_id, {"type": "pong", "timestamp": datetime.utcnow().isoformat()})
        
        elif message_type == "get_lobby_stats":
            stats = await self._get_lobby_statistics(db)
            await self._send_to_player(player_id, {
                "type": "lobby_stats",
                "data": stats.to_dict()
            })
        
        elif message_type == "get_queue_status":
            queue_status = await self._get_matchmaking_queue_status(db)
            await self._send_to_player(player_id, {
                "type": "queue_status", 
                "data": queue_status
            })
        
        elif message_type == "chat_message":
            await self._handle_lobby_chat(player_id, message.get("content", ""))
        
        elif message_type == "challenge_player":
            target_player_id = message.get("target_player_id")
            await self._handle_player_challenge(player_id, target_player_id)
        
        else:
            logger.warning(f"Unknown message type from player {player_id}: {message_type}")
    
    async def _send_initial_lobby_state(self, websocket: WebSocket, db: Session):
        """Send complete lobby state to newly connected player"""
        
        # Get current players
        players_data = [player.to_dict() for player in self.lobby_players.values()]
        
        # Get lobby statistics
        stats = await self._get_lobby_statistics(db)
        
        # Get queue status
        queue_status = await self._get_matchmaking_queue_status(db)
        
        initial_state = {
            "type": "lobby_state",
            "data": {
                "players": players_data,
                "stats": stats.to_dict(),
                "queue_status": queue_status,
                "server_time": datetime.utcnow().isoformat()
            }
        }
        
        await websocket.send_text(json.dumps(initial_state))
    
    async def _broadcast_player_update(self, player: LobbyPlayer, action: str):
        """Broadcast player updates to all connected players"""
        
        message = {
            "type": "player_update",
            "action": action,  # "joined", "left", "updated"
            "player": player.to_dict()
        }
        
        await self._broadcast_to_all(message)
    
    async def _broadcast_to_all(self, message: Dict):
        """Send message to all connected players"""
        
        if not self.active_connections:
            return
        
        message_text = json.dumps(message)
        disconnected_players = []
        
        for player_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                logger.warning(f"Failed to send message to player {player_id}: {e}")
                disconnected_players.append(player_id)
        
        # Clean up disconnected players
        for player_id in disconnected_players:
            await self.disconnect_player(player_id)
    
    async def _send_to_player(self, player_id: int, message: Dict):
        """Send message to specific player"""
        
        if player_id in self.active_connections:
            try:
                await self.active_connections[player_id].send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send message to player {player_id}: {e}")
                await self.disconnect_player(player_id)
    
    async def _periodic_updates(self, db: Session):
        """Periodic background updates for lobby"""
        
        try:
            while self.active_connections:
                # Update lobby statistics
                stats = await self._get_lobby_statistics(db)
                await self._broadcast_to_all({
                    "type": "stats_update",
                    "data": stats.to_dict()
                })
                
                # Update queue status
                queue_status = await self._get_matchmaking_queue_status(db)
                await self._broadcast_to_all({
                    "type": "queue_update", 
                    "data": queue_status
                })
                
                await asyncio.sleep(self.stats_update_interval)
                
        except asyncio.CancelledError:
            logger.info("Lobby periodic updates cancelled")
        except Exception as e:
            logger.error(f"Error in lobby periodic updates: {e}")
    
    async def _get_lobby_statistics(self, db: Session) -> LobbyStats:
        """Calculate current lobby statistics"""
        
        # Count players by status
        status_counts = {"idle": 0, "searching": 0, "in_game": 0}
        for player in self.lobby_players.values():
            status_counts[player.status] = status_counts.get(player.status, 0) + 1
        
        # Get queue statistics from database
        queue_stats = db.query(PlayerQueue).filter(
            PlayerQueue.status == MatchmakingStatus.SEARCHING
        ).all()
        
        # Calculate average wait time
        avg_wait_time = 0.0
        if queue_stats:
            total_wait = sum(
                (datetime.utcnow() - q.joined_at).total_seconds() 
                for q in queue_stats
            )
            avg_wait_time = total_wait / len(queue_stats)
        
        # Queue breakdown by type
        queue_breakdown = {}
        for queue_entry in queue_stats:
            queue_type = queue_entry.queue_type
            queue_breakdown[queue_type] = queue_breakdown.get(queue_type, 0) + 1
        
        # Recent matches (last hour)
        from app.models.matchmaking import MatchmakingHistory
        recent_matches = db.query(MatchmakingHistory).filter(
            MatchmakingHistory.created_at >= datetime.utcnow() - timedelta(hours=1)
        ).count()
        
        return LobbyStats(
            total_players=len(self.lobby_players),
            searching_players=status_counts["searching"],
            avg_wait_time=avg_wait_time,
            queue_breakdown=queue_breakdown,
            recent_matches=recent_matches
        )
    
    async def _get_matchmaking_queue_status(self, db: Session) -> Dict:
        """Get detailed matchmaking queue information"""
        
        from app.services.matchmaking_service import matchmaking_service
        return matchmaking_service.get_queue_status(db)
    
    async def _handle_lobby_chat(self, player_id: int, content: str):
        """Handle lobby chat messages"""
        
        if player_id not in self.lobby_players:
            return
        
        player = self.lobby_players[player_id]
        
        # Basic content filtering
        if len(content.strip()) == 0 or len(content) > 200:
            return
        
        chat_message = {
            "type": "chat_message",
            "data": {
                "player_id": player_id,
                "username": player.username,
                "content": content.strip(),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        await self._broadcast_to_all(chat_message)
    
    async def _handle_player_challenge(self, challenger_id: int, target_id: int):
        """Handle direct player challenges"""
        
        if challenger_id not in self.lobby_players or target_id not in self.lobby_players:
            return
        
        challenger = self.lobby_players[challenger_id]
        target = self.lobby_players[target_id]
        
        # Send challenge to target player
        challenge_message = {
            "type": "player_challenge",
            "data": {
                "challenger_id": challenger_id,
                "challenger_username": challenger.username,
                "challenger_rating": challenger.rating,
                "challenge_id": f"{challenger_id}_{target_id}_{int(datetime.utcnow().timestamp())}"
            }
        }
        
        await self._send_to_player(target_id, challenge_message)
        
        # Notify challenger that challenge was sent
        await self._send_to_player(challenger_id, {
            "type": "challenge_sent",
            "data": {
                "target_username": target.username,
                "target_rating": target.rating
            }
        })
    
    async def broadcast_match_found(self, player1_id: int, player2_id: int, game_id: int):
        """Broadcast when a match is found"""
        
        message = {
            "type": "match_found",
            "data": {
                "game_id": game_id,
                "players": [player1_id, player2_id],
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        # Send to both matched players
        for player_id in [player1_id, player2_id]:
            await self._send_to_player(player_id, message)
        
        # Update their status
        await self.update_player_status(player1_id, "in_game")
        await self.update_player_status(player2_id, "in_game")
    
    def get_connected_players(self) -> List[Dict]:
        """Get list of all connected players"""
        return [player.to_dict() for player in self.lobby_players.values()]


# Global lobby manager instance
lobby_manager = LobbyConnectionManager()