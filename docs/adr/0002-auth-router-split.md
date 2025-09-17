# 0002 - Auth Router Split

Date: 2025-09-17

Status: Accepted

Context
-------

The authentication system in GesahniV2 had grown into a monolithic `app/api/auth.py` file
containing over 2,500 lines with mixed concerns: endpoint definitions, business logic,
error handling, metrics, and deprecated compatibility code. This created several issues:

- **Maintenance burden**: Large single file made it difficult to navigate and modify
  auth-related code
- **Testing complexity**: All auth endpoints shared the same module scope, making
  isolated testing challenging
- **Code organization**: Business logic, routing, and compatibility concerns were
  tightly coupled
- **Scalability**: Adding new auth features required modifying the monolithic file

Decision
--------

We split the authentication system into a modular architecture under `app/auth/`:

**Core Structure:**
```
app/auth/
├── endpoints/           # Individual endpoint modules
│   ├── __init__.py      # Router aggregation with tags=["Auth"]
│   ├── login.py         # Login endpoints (/auth/login)
│   ├── register.py      # Registration endpoints (/register)
│   ├── refresh.py       # Token refresh endpoints (/auth/refresh)
│   ├── logout.py        # Logout endpoints (/auth/logout, /auth/logout_all)
│   ├── token.py         # Token management (/auth/token, /auth/examples)
│   └── debug.py         # Debug endpoints (/whoami, /debug/*)
├── errors.py            # Centralized error code constants
├── models.py            # Pydantic models (WhoAmIOut, RefreshOut, etc.)
├── service.py           # Shared business logic and helpers
├── jwt_utils.py         # JWT token utilities
├── cookie_utils.py      # Cookie handling utilities
└── whoami_impl.py       # Whoami endpoint implementation
```

**Key Design Principles:**
- Each endpoint module focuses on a single concern
- Shared logic extracted to `service.py` and utility modules
- All modules use consistent `tags=["Auth"]` for OpenAPI grouping
- Error codes centralized in `errors.py` for consistency
- Response models in `models.py` for client codegen

**Legacy Compatibility:**
- `app/api/auth.py` maintains backward compatibility with deprecation warnings
- Legacy imports trigger logger warnings pointing to new locations
- All existing endpoints remain functional during transition period

Rationale
---------

- **Separation of concerns**: Each module handles one aspect of authentication,
  making the codebase more maintainable and testable
- **OpenAPI organization**: Consistent tagging ensures auth endpoints appear
  together in generated documentation
- **Client codegen**: Structured response models enable better TypeScript/FastAPI
  client generation
- **Incremental migration**: Legacy compatibility ensures no breaking changes
  for existing integrations
- **Testability**: Smaller, focused modules are easier to unit test in isolation

How to Add a New Auth Endpoint
------------------------------

1. **Choose the appropriate module** or create a new one under `app/auth/endpoints/`
2. **Define your endpoint** with proper decorators:
   ```python
   from app.auth_protection import public_route  # or auth_only_route
   from app.auth.errors import ERR_YOUR_ERROR_CODE

   @router.post("/auth/your-endpoint")
   @public_route  # or @auth_only_route
   async def your_endpoint(request: Request, response: Response):
       # Implementation
   ```
3. **Add response model** to `app/auth/models.py` if needed:
   ```python
   class YourEndpointOut(BaseModel):
       result: str
   ```
4. **Update imports** in `app/auth/endpoints/__init__.py`
5. **Add tests** in `tests/auth/` following the module structure
6. **Update documentation** if the endpoint changes the auth contract

Consequences
------------

- **Improved maintainability**: Auth code is now organized by concern
- **Better testing**: Smaller modules enable focused unit tests
- **Enhanced documentation**: Consistent tagging and models improve API docs
- **Migration path**: Deprecation warnings guide users to new import locations
- **Future work**: This foundation enables further auth system improvements
  like OAuth provider modularization and advanced session management
