from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class LeaderboardCache(Base):
    __tablename__ = "leaderboard_cache"

    cache_key = Column(String(100), primary_key=True)
    data = Column(Text, nullable=False)  # JSON data
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __init__(self, cache_key: str, data: str, expires_at: DateTime):
        self.cache_key = cache_key
        self.data = data
        self.expires_at = expires_at