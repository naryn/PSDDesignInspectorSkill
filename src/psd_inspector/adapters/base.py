"""Base adapter for PSD parsing with standardized interface."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path

from ..models.document import DocumentMetadata, Artboard, CoordinateSpace


class ParseError(Exception):
    """Exception raised for parsing errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedFeatureError(ParseError):
    """Exception for unsupported PSD features."""
    pass


class PSDBaseAdapter(ABC):
    """Abstract base class for PSD parsers.
    
    All adapters must implement these core methods to provide
    a unified interface for the extraction pipeline.
    """
    
    SUPPORTED_FORMATS = [".psd", ".psb"]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize adapter with optional configuration.
        
        Args:
            config: Adapter-specific configuration options
        """
        self.config = config or {}
        self._supported_features: List[str] = []
        self._unsupported_features: List[str] = []
    
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this adapter can parse the given file.
        
        Args:
            file_path: Path to PSD file
            
        Returns:
            True if adapter supports this file format
        """
        pass
    
    @abstractmethod
    def parse(self, file_path: Path) -> DocumentMetadata:
        """Parse document-level metadata.
        
        Args:
            file_path: Path to PSD file
            
        Returns:
            Parsed document metadata
            
        Raises:
            ParseError: If file cannot be parsed
            UnsupportedFeatureError: If required features not supported
        """
        pass
    
    @abstractmethod
    def get_layers(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extract all layers from PSD.
        
        Args:
            file_path: Path to PSD file
            
        Returns:
            List of layer dictionaries with raw properties
            
        Raises:
            ParseError: If layers cannot be extracted
        """
        pass
    
    @abstractmethod
    def get_artboards(self, file_path: Path) -> List[Artboard]:
        """Extract artboards from document.
        
        Args:
            file_path: Path to PSD file
            
        Returns:
            List of artboard definitions
        """
        pass
    
    @abstractmethod
    def get_coordinate_spaces(self, file_path: Path) -> List[CoordinateSpace]:
        """Extract coordinate space definitions.
        
        Args:
            file_path: Path to PSD file
            
        Returns:
            List of coordinate space definitions
        """
        pass
    
    def get_supported_features(self) -> List[str]:
        """Get list of supported features.
        
        Returns:
            List of feature names this adapter can handle
        """
        return self._supported_features.copy()
    
    def get_unsupported_features(self) -> List[str]:
        """Get list of unsupported features.
        
        Returns:
            List of unsupported feature names
        """
        return self._unsupported_features.copy()
    
    def validate_file(self, file_path: Path) -> bool:
        """Validate file format and accessibility.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is valid and accessible
        """
        if not file_path.exists():
            return False
        
        if not any(file_path.suffix.lower() == fmt for fmt in self.SUPPORTED_FORMATS):
            return False
        
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                # Check for Photoshop signature
                if not self._is_psdsignature(header):
                    return False
            return True
        except (IOError, PermissionError):
            return False
    
    @staticmethod
    @abstractmethod
    def _is_psdsignature(header: bytes) -> bool:
        """Check if header indicates valid Photoshop file.
        
        Args:
            header: First 4 bytes of file
            
        Returns:
            True if valid PSD signature
        """
        pass
    
    def close(self):
        """Clean up resources. Override in subclasses if needed."""
        pass
