from django import forms
from django.conf import settings


class UploadForm(forms.Form):
    file = forms.FileField(
        label="Session file",
        help_text="A JSONL file from your coding harness.",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        max_bytes = settings.SESSIONBIN["MAX_UPLOAD_BYTES"]
        if f.size > max_bytes:
            raise forms.ValidationError(
                f"File is too large. Maximum is {max_bytes // (1024 * 1024)} MB."
            )
        return f
