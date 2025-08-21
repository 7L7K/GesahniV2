# Refactoring Summary: Structured Logging and Memory Write Policies

This document summarizes the comprehensive refactoring changes made to implement the requested improvements:

## 1. Replace Print with Structured Logger

### Enhanced Logging Configuration (`app/logging_config.py`)
- **Added `DebugBannerFormatter`**: New formatter that adds emoji/debug banners for local development
- **Environment Variable**: Added `DEBUG_BANNERS` env var to control emoji/debug banners (default: false)
- **Structured Logging**: Enhanced logging with structured metadata and request ID tracking
- **Flexible Output**: Supports both JSON (production) and human-readable (development) formats

### Replaced Print Statements
The following files had print statements replaced with structured logging:

#### `app/router.py`
- Model routing decisions and trace logging
- GPT/LLaMA call logging with metadata
- Golden trace logging for auditability

#### `app/api/ask.py`
- API entry point logging with payload details
- Request processing metadata

#### `app/api/auth.py`
- Authentication flow logging
- Cookie setting/clearing operations
- Refresh token operations
- Clerk callback debugging

#### `app/model_picker.py`
- Model selection decisions with detailed metadata
- Routing logic explanations

#### `app/auth.py`
- Login cookie operations
- Error handling and fallback scenarios

#### `app/main.py`
- Health check status logging

#### `app/csrf.py`
- CSRF deprecation warnings

#### `app/auth_device/__init__.py`
- Device trust warnings

## 2. Environment Variable for Debug Banners

### New Environment Variable
- **`DEBUG_BANNERS`**: Controls emoji/debug banners in logs
  - Values: `1`, `true`, `yes`, `on` (enables banners)
  - Default: `false` (no banners)
  - Usage: `DEBUG_BANNERS=1` for local development

### Banner Examples
- 🔍 DEBUG: Debug messages
- ℹ️ INFO: Information messages  
- ⚠️ WARNING: Warning messages
- ❌ ERROR: Error messages
- 🚨 CRITICAL: Critical messages

## 3. Make User_ID Explicit (No Depends)

### Updated API Routes
- **`app/api/ask.py`**: Modified `_ask` function to resolve `user_id` explicitly from request
- **Removed `Depends(get_current_user_id)`**: User ID is now resolved within the function body
- **Maintained Backward Compatibility**: All existing functionality preserved

### Pattern Applied
```python
# Before
async def _ask(request: Request, body: dict | None, user_id: str = Depends(get_current_user_id)):

# After  
async def _ask(request: Request, body: dict | None):
    """Internal ask function that accepts resolved user_id parameter."""
    # Resolve user_id from request
    user_id = await get_current_user_id(request)
```

## 4. Delete Unused Imports and Dead Helpers

### Removed Unused Imports
- **`app/router.py`**: Removed `Depends` import from FastAPI
- **`app/router.py`**: Removed `get_current_user_id` import

### Removed Dead Code
- **`app/router.py`**: Removed `_annotate_provenance` function (unused)
- **`app/main.py`**: Updated imports to use renamed functions

## 5. Guard Memory/Profile Writes Behind Policy

### New Memory Write Policy Module (`app/memory/write_policy.py`)

#### Policy Features
- **Response Length Checks**: Minimum character requirements for memory/profile writes
- **Low Confidence Detection**: Regex patterns to identify uncertain responses
- **Confidence Score Validation**: Optional confidence thresholds
- **Configurable Thresholds**: Environment variables for customization

#### Environment Variables
- **`MEMORY_MIN_RESPONSE_LENGTH`**: Minimum response length for memory writes (default: 50)
- **`PROFILE_MIN_RESPONSE_LENGTH`**: Minimum response length for profile writes (default: 20)
- **`ENABLE_MEMORY_WRITE_POLICY`**: Enable/disable memory write policy (default: 1)
- **`ENABLE_PROFILE_WRITE_POLICY`**: Enable/disable profile write policy (default: 1)

#### Low Confidence Indicators
- "I don't know", "I'm not sure", "I can't"
- "No information", "not available", "not found"
- "Error", "failed", "unavailable", "offline"
- "Please try", "please check", "please verify"
- "Contact support", "contact admin"

### Updated Memory Write Operations

#### Router Memory Writes
- **GPT Override Calls**: Added policy checks before memory writes
- **LLaMA Override Calls**: Added policy checks before memory writes
- **Default GPT Calls**: Added policy checks before memory writes
- **Default LLaMA Calls**: Added policy checks before memory writes

#### Profile Store Operations
- **Profile Updates**: Added policy checks in `_maybe_update_profile_from_statement`
- **Proactive Engine**: Added policy checks for profile and memory writes

#### Pattern Applied
```python
# Before
add_user_memory(user_id, _fact_from_qa(prompt, text))

# After
if memory_write_policy.should_write_memory(text):
    add_user_memory(user_id, _fact_from_qa(prompt, text))
else:
    logger.debug("Memory write blocked by policy for GPT response")
```

## 6. Testing

### New Test Suite (`tests/unit/test_memory_write_policy.py`)
- **11 comprehensive tests** covering all policy scenarios
- **Response length validation**
- **Low confidence detection**
- **Confidence score validation**
- **Empty response handling**
- **Profile write policies**

### Test Coverage
- ✅ Short response blocking
- ✅ Long response allowing
- ✅ Low confidence indicator detection
- ✅ Acknowledgment blocking
- ✅ Punctuation-only blocking
- ✅ Confidence score validation
- ✅ Empty response handling
- ✅ Profile write policies

## 7. Benefits Achieved

### Improved Observability
- **Structured Logging**: Better log parsing and analysis
- **Request Tracing**: Full request lifecycle tracking
- **Debug Banners**: Enhanced local development experience
- **Metadata Enrichment**: Contextual information in logs

### Better Memory Management
- **Quality Control**: Prevents low-quality memory writes
- **Storage Efficiency**: Reduces noise in memory stores
- **Configurable Policies**: Environment-based tuning
- **Confidence Validation**: Optional confidence-based filtering

### Enhanced Maintainability
- **Explicit Dependencies**: Clearer function signatures
- **Removed Dead Code**: Cleaner codebase
- **Comprehensive Testing**: Validated functionality
- **Documentation**: Clear implementation details

### Development Experience
- **Debug Banners**: Visual indicators for log levels
- **Flexible Logging**: JSON for production, readable for development
- **Environment Control**: Easy toggling of features
- **Error Tracking**: Enhanced error monitoring capabilities

## 8. Migration Notes

### Environment Variables
Add to your environment configuration:
```bash
# Enable debug banners for local development
DEBUG_BANNERS=1

# Configure memory write policies
MEMORY_MIN_RESPONSE_LENGTH=50
PROFILE_MIN_RESPONSE_LENGTH=20
ENABLE_MEMORY_WRITE_POLICY=1
ENABLE_PROFILE_WRITE_POLICY=1
```

### Backward Compatibility
- All existing API endpoints maintain the same interface
- Authentication flows unchanged
- Memory operations continue to work (with added quality gates)
- Logging format changes are transparent to clients

### Performance Impact
- **Minimal**: Policy checks are lightweight regex operations
- **Configurable**: Policies can be disabled if needed
- **Efficient**: Early returns prevent unnecessary processing

## 9. Future Enhancements

### Potential Improvements
- **Machine Learning**: Confidence scoring based on response patterns
- **User Feedback**: Integration with user feedback for policy tuning
- **A/B Testing**: Policy effectiveness measurement
- **Advanced Patterns**: More sophisticated low-confidence detection
- **Metrics**: Policy decision tracking and analytics

### Monitoring
- **Policy Decisions**: Track when writes are blocked/allowed
- **Response Quality**: Monitor response length and confidence distributions
- **User Experience**: Measure impact on user satisfaction
- **Storage Efficiency**: Track memory store growth rates
