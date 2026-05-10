# routers.py - Unified Database Router

class DatabaseRouter:
    """
    Unified database router for all apps.
    Routes live_operations to ereunify, everything else to default.
    """
    
    # Apps that use the live MSSQL database
    LIVE_APPS = [
        'live_operations',
        'apps.live_operations',
    ]
    
    def db_for_read(self, model, **hints):
        """Route read operations"""
        app_label = model._meta.app_label
        
        if app_label in self.LIVE_APPS:
            return 'ereunify'
        return 'default'
    
    def db_for_write(self, model, **hints):
        """Route write operations"""
        app_label = model._meta.app_label
        
        if app_label in self.LIVE_APPS:
            return 'ereunify'
        return 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects"""
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Control migrations"""
        if db == 'ereunify':
            # Never run migrations on live production database
            return False
        if db == 'default':
            return True
        return None