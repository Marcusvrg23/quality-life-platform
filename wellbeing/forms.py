"""Break reminder form (docs/specs/13-pwa-lembretes.md)."""

from django import forms

from .models import REMINDER_INTERVALS, shift_minutes

WEEKDAYS = (
    ("1", "Seg"),
    ("2", "Ter"),
    ("3", "Qua"),
    ("4", "Qui"),
    ("5", "Sex"),
    ("6", "Sáb"),
    ("7", "Dom"),
)
# Deactivation is a separate form handled by the view before validation.
ACTIONS = ("activate", "save")
# Safari on iOS may send the <input type="time"> value with seconds or
# milliseconds ("09:30:00", "09:30:00.000"); only hour:minute is kept.
TIME_FORMATS = ["%H:%M", "%H:%M:%S", "%H:%M:%S.%f"]


class MinuteTimeField(forms.TimeField):
    def to_python(self, value):
        parsed = super().to_python(value)
        return parsed.replace(second=0, microsecond=0) if parsed else parsed


def _time_field(label):
    return MinuteTimeField(
        input_formats=TIME_FORMATS,
        error_messages={
            "required": f"Informe o {label} do expediente.",
            "invalid": f"Horário de {label} inválido.",
        },
    )


class ReminderForm(forms.Form):
    action = forms.ChoiceField(
        choices=[(action, action) for action in ACTIONS],
        error_messages={"invalid_choice": "Ação inválida."},
    )
    interval_minutes = forms.TypedChoiceField(
        choices=[(str(minutes), f"{minutes} min") for minutes in REMINDER_INTERVALS],
        coerce=int,
        error_messages={
            "required": "Escolha um intervalo de 60, 90 ou 120 min.",
            "invalid_choice": "Escolha um intervalo de 60, 90 ou 120 min.",
        },
    )
    workday_start = _time_field("início")
    workday_end = _time_field("fim")
    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAYS,
        error_messages={
            "required": "Escolha pelo menos um dia.",
            "invalid_choice": "Escolha dias entre segunda e domingo.",
        },
    )

    def clean(self):
        data = super().clean()
        start, end = data.get("workday_start"), data.get("workday_end")
        interval = data.get("interval_minutes")
        if start and end:
            if start == end:
                raise forms.ValidationError(
                    "O início e o fim do expediente precisam ser diferentes."
                )
            # An end at or before the start finishes on the next day; at least
            # one reminder must fall strictly between start and end.
            if interval and shift_minutes(start, end) <= interval:
                raise forms.ValidationError(
                    "O expediente precisa ser maior que o intervalo."
                )
        return data

    def first_error(self):
        """The message shown on a refused POST: shift rules, then fields."""
        if self.non_field_errors():
            return self.non_field_errors()[0]
        for name in self.fields:
            if name in self.errors:
                return self.errors[name][0]
        return "Confira o intervalo, os horários e os dias escolhidos."

    def weekday_digits(self):
        return "".join(sorted(set(self.cleaned_data["weekdays"])))
