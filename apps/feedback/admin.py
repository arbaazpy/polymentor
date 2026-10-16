from django.contrib import admin, messages

from apps.feedback import services
from apps.feedback.models import Feedback, LearnedExemplar


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("created_at", "expert_key", "rating", "mined", "turn")
    list_filter = ("rating", "expert_key", "mined")
    raw_id_fields = ("turn",)
    actions = ("mine",)

    @admin.action(description="Mine all unmined feedback into pending exemplars")
    def mine(self, request, queryset):
        # Mines every unmined row, not only the selection, matching `manage.py mine_feedback`.
        counts = services.mine_feedback()
        self.message_user(
            request,
            f"Created {counts['created']} pending exemplars, skipped {counts['skipped']}.",
            messages.SUCCESS,
        )


@admin.register(LearnedExemplar)
class LearnedExemplarAdmin(admin.ModelAdmin):
    list_display = ("created_at", "expert_key", "status", "question")
    list_filter = ("status", "expert_key")
    search_fields = ("question", "answer")
    actions = ("approve", "reject")

    @admin.action(description="Approve (adds to grounding immediately)")
    def approve(self, request, queryset):
        queryset.update(status=LearnedExemplar.Status.APPROVED)

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        queryset.update(status=LearnedExemplar.Status.REJECTED)
