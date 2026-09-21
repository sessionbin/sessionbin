(function () {
    var COPY_ICON =
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"' +
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
        ' stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>' +
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

    var CHECK_ICON =
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"' +
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
        ' stroke-linejoin="round" aria-hidden="true">' +
        '<polyline points="20 6 9 17 4 12"/></svg>';

    function asText(btn, copied) {
        btn.textContent = copied ? "Copied" : "Copy";
    }

    /* An icon button says nothing on its own, so the confirmation a reader can see is the
       glyph turning into a tick. What a screen reader hears is the status line below,
       which both kinds of button share. */
    function asIcon(btn, copied) {
        btn.innerHTML = copied ? CHECK_ICON : COPY_ICON;
        btn.classList.toggle("is-copied", copied);
    }

    function wire(btn, status, noun, text, label) {
        var timer;

        function reset() {
            clearTimeout(timer);
            label(btn, false);
            status.textContent = "";
            status.classList.add("visually-hidden");
        }

        function succeeded() {
            label(btn, true);
            status.textContent = "Copied to clipboard";
            timer = setTimeout(reset, 1500);
        }

        /* Left standing rather than flashed for a second: someone who missed it would
           go on believing they hold the only copy of a URL they never copied. */
        function failed() {
            status.textContent = "Copy failed — select the " + noun + " and copy it yourself.";
            status.classList.remove("visually-hidden");
        }

        btn.addEventListener("click", function () {
            reset();
            // Undefined outside a secure context, which a self-hosted instance over
            // plain HTTP is.
            if (!navigator.clipboard) {
                failed();
                return;
            }
            navigator.clipboard.writeText(text()).then(succeeded, failed);
        });
    }

    document.querySelectorAll("button[data-copy]").forEach(function (btn) {
        wire(btn, btn.parentNode.querySelector(".copy-status"), "link", function () {
            return btn.getAttribute("data-copy");
        }, asText);
    });

    /* Built here rather than written into the template: what lands in the clipboard is
       then the block's own text, which cannot drift from what is on screen, and the
       "$ " prompt is drawn by CSS so it never comes along. */
    document.querySelectorAll("pre.shell").forEach(function (pre) {
        var wrap = document.createElement("div");
        var btn = document.createElement("button");
        var status = document.createElement("span");

        wrap.className = "snippet";
        btn.type = "button";
        btn.className = "btn-copy-icon";
        btn.setAttribute("aria-label", "Copy command");
        asIcon(btn, false);
        status.className = "copy-status visually-hidden";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");

        pre.parentNode.insertBefore(wrap, pre);
        wrap.appendChild(pre);
        wrap.appendChild(btn);
        wrap.appendChild(status);

        wire(btn, status, "command", function () {
            return pre.textContent.trim();
        }, asIcon);
    });
})();
