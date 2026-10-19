"""``{{ tenant|assistant_on }}``: whether the menu shows the assistant (spec 18)."""

from django import template

from wellbeing import assistant

register = template.Library()


@register.filter
def assistant_on(tenant):
    return bool(tenant) and assistant.enabled_for(tenant.organization)
