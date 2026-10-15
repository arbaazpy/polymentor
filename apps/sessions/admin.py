from django.contrib import admin

from apps.sessions.models import Turn


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ("created_at", "prompt", "status", "latency_ms", "is_example")
    list_filter = ("status", "is_example")
    list_editable = ("is_example",)
    search_fields = ("prompt",)
