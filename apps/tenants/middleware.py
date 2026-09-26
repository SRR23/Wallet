"""
Tenant middleware.

Prefer TenantHeaderAuthentication on DRF views. Only register middleware
here if non-DRF code also needs request.tenant.
"""
