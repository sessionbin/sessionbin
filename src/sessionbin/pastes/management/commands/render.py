import gzip
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sessionbin.adapters import parse as adapter_parse
from sessionbin.pastes.models import Paste
from sessionbin.pastes.render import RENDERER_VERSION, render


class Command(BaseCommand):
    help = "Re-render stored session files to HTML fragments."

    def add_arguments(self, parser):
        parser.add_argument(
            "slug",
            nargs="?",
            help="Slug to re-render (e.g. 63w3ktkgjf or 63w3ktkgjf.jsonl.gz). "
            "Omit to re-render all.",
        )

    def handle(self, *, slug, **options):
        data_dir: Path = settings.SESSIONBIN["DATA_DIR"]
        raw_dir = data_dir / "raw"
        fragment_dir = data_dir / "fragments"

        if slug:
            slug = slug.removesuffix(".jsonl.gz").removesuffix(".jsonl")
            src = raw_dir / f"{slug}.jsonl.gz"
            if not src.exists():
                raise CommandError(f"Raw file not found: {src}")
            self._render_file(src, fragment_dir / f"{slug}.html")
        else:
            files = sorted(raw_dir.glob("*.jsonl.gz"))
            if not files:
                raise CommandError(f"No .jsonl.gz files found in {raw_dir}")
            fragment_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                self._render_file(f, fragment_dir / f"{f.stem.removesuffix('.jsonl')}.html")
            self.stdout.write(f"Rendered {len(files)} fragments.")

    def _render_file(self, src: Path, dest: Path) -> None:
        raw = gzip.decompress(src.read_bytes())
        paste = Paste.objects.filter(slug=dest.stem).first()
        session, adapter_version = adapter_parse(raw, harness=paste.harness if paste else None)
        dest.write_text(render(session))
        if paste:
            paste.renderer_version = RENDERER_VERSION
            paste.adapter_version = adapter_version
            paste.turn_count = session.turn_count
            paste.tool_call_count = session.tool_call_count
            paste.save(
                update_fields=[
                    "renderer_version",
                    "adapter_version",
                    "turn_count",
                    "tool_call_count",
                ]
            )
        self.stderr.write(f"  {dest.name}\n")
