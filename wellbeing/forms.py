"""Break reminder form (docs/specs/13-pwa-lembretes.md)."""

from django import forms

from .models import REMINDER_INTERVALS

WEEKDAYS = (
    ("1", "Seg"),
    ("2", "Ter"),
    ("3", "Qua"),
    ("4", "Qui"),
    ("5", "Sex"),
    ("6", "Sáb"),
    ("7", "Dom"),
)
ACTIONS = ("activate", "save", "deactivate")


class ReminderForm(forms.Form):
    action = forms.ChoiceField(choices=[(action, action) for action in ACTIONS])
    interval_minutes = forms.TypedChoiceField(
        choices=[(str(minutes), f"{minutes} min") for minutes in REMINDER_INTERVALS],
        coerce=int,
    )
    workday_start = forms.TimeField(input_formats=["%H:%M"])
    workday_end = forms.TimeField(input_formats=["%H:%M"])
    weekdays = forms.MultipleChoiceField(choices=WEEKDAYS)

    def clean(self):
        data = super().clean()
        start, end = data.get("workday_start"), data.get("workday_end")
        interval = data.get("interval_minutes")
        if start and end and interval:
            span = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
            # At least one reminder strictly between start and end.
            if span <= interval:
                raise forms.ValidationError(
                    "O expediente precisa ser maior que o intervalo."
                )
        return data

    def weekday_digits(self):
        return "".join(sorted(set(self.cleaned_data["weekdays"])))
