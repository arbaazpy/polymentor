from django.contrib import admin

from apps.experts.models import Expert, ExpertVersion


class ExpertVersionInline(admin.TabularInline):
    model = ExpertVersion
    extra = 0
    fields = ("semver", "status", "nugen_model_id", "base_model", "gate_reason", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ("key", "lane", "current_version")
    inlines = (ExpertVersionInline,)


@admin.register(ExpertVersion)
class ExpertVersionAdmin(admin.ModelAdmin):
    list_display = ("expert", "semver", "status", "nugen_model_id", "created_at")
    list_filter = ("status", "expert")
    readonly_fields = ("metrics",)
