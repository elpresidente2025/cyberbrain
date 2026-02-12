
from typing import Dict, Any, Optional

class Agent:
    def __init__(self, name: str, options: Optional[Dict[str, Any]] = None):
        self.name = name
        self.options = options or {}
    
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Default run method delegates to process"""
        return await self.process(context)
    
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement process method")
