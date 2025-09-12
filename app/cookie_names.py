# Cookie names module - re-export from web.cookies for backward compatibility

from .web.cookies import NAMES

# Extract individual names for backward compatibility
GSNH_AT = NAMES.access
GSNH_RT = NAMES.refresh
GSNH_SESS = NAMES.session

__all__ = ["NAMES", "GSNH_AT", "GSNH_RT", "GSNH_SESS"]
