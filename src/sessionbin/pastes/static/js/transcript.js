/* The transcript header pins itself to the top and compacts once it is stuck. This runs
   for every transcript, including ones with no user turns to navigate. */
(function () {
    var header = document.querySelector('.transcript .header');
    if (!header) return;

    var queued = false;

    function sync() {
        header.classList.toggle('is-stuck', header.getBoundingClientRect().top <= 0);
    }

    window.addEventListener(
        'scroll',
        function () {
            if (queued) return;
            queued = true;
            requestAnimationFrame(function () {
                queued = false;
                sync();
            });
        },
        { passive: true }
    );

    sync();
})();

/* Progressive enhancement for the user-turn navigator. The index is a <details> and
   works without any of this; what needs script is knowing where the reader currently is.
   The steppers stay hidden until they work. */
(function () {
    var nav = document.querySelector('.prompt-nav');
    if (!nav) return;

    var index = nav.querySelector('.prompt-index');
    var summary = index.querySelector('summary');
    var marker = nav.querySelector('.prompt-marker');
    var steppers = nav.querySelectorAll('.prompt-step');
    var items = [];

    nav.querySelectorAll('[data-prompt-link]').forEach(function (link) {
        var target = document.getElementById(link.getAttribute('data-prompt-link'));
        if (target) items.push({ link: link, row: link.parentElement, target: target });
    });
    if (!items.length) return;

    var current = -1;
    // The turn the reader asked for, and the scroll position it parked at. Null means
    // the position is not known yet, which is the case until the jump has settled.
    var chosen = -1;
    var chosenAt = null;

    // "10 / 11" is a character wider than "9 / 11", and letting the readout grow would
    // shove the buttons sideways as the reader scrolls past the tenth turn. The font is
    // monospaced, so ch is exact.
    marker.style.minWidth = String(items.length).length * 2 + 3 + 'ch';

    // Where a jump parks a turn, read from the stylesheet. Using the header's height
    // instead would put the line above where turns land, so the turn just jumped to
    // would not register and the steppers would count from the one before it.
    var jumpLine = parseFloat(getComputedStyle(items[0].target).scrollMarginTop) + 4;

    // aria-disabled, not the disabled property: a disabled button takes no pointer
    // events, so it could not be hovered for its tooltip. go() ignores the click.
    function setUnavailable(button, off) {
        button.setAttribute('aria-disabled', off ? 'true' : 'false');
    }

    function unavailable(button) {
        return button.getAttribute('aria-disabled') === 'true';
    }

    function targetIndex(button) {
        var step = button.getAttribute('data-prompt-step');
        if (step === 'first') return 0;
        if (step === 'last') return items.length - 1;
        return current + Number(step);
    }

    function indexForHash() {
        var id = window.location.hash.slice(1);
        for (var i = 0; i < items.length; i++) {
            if (items[i].target.id === id) return i;
        }
        return -1;
    }

    function choose(n) {
        chosen = n;
        chosenAt = null;
    }

    function closeIndex(restoreFocus) {
        if (!index.open) return;
        var hadFocus = index.contains(document.activeElement);
        index.open = false;
        // Closing hides whatever was focused inside, which would otherwise drop the
        // reader at the top of the tab order.
        if (restoreFocus && hadFocus) summary.focus();
    }

    function go(n) {
        if (n < 0 || n >= items.length) return;
        closeIndex(false);
        choose(n);
        var target = items[n].target;
        if (window.location.hash === '#' + target.id) {
            // Assigning the hash it already holds moves nothing, so scroll it directly.
            target.scrollIntoView();
        } else {
            // Via the hash so the turn gets the same :target flash as a shared link.
            window.location.hash = target.id;
        }
        update();
    }

    function update() {
        var found = 0;
        for (var i = 0; i < items.length; i++) {
            if (items[i].target.getBoundingClientRect().top <= jumpLine) found = i;
        }
        // Asking for a turn settles it. Every turn in the last screenful shares one
        // scroll position, and on a transcript that fits the window they all do, so the
        // line cannot separate them and only the reader's own choice can.
        var maxScroll = document.documentElement.scrollHeight - window.innerHeight;
        if (chosen >= 0) {
            found = chosen;
        } else if (maxScroll > 2 && window.scrollY >= maxScroll - 2) {
            found = items.length - 1;
        }
        if (found !== current) {
            if (current >= 0) items[current].row.classList.remove('is-current');
            items[found].row.classList.add('is-current');
            marker.textContent = found + 1 + ' / ' + items.length;
            current = found;
        }
        steppers.forEach(function (button) {
            var n = targetIndex(button);
            setUnavailable(button, n < 0 || n >= items.length || n === current);
        });
    }

    // One turn means nothing to step between, so the arrows would only ever be dead.
    if (items.length > 1) {
        steppers.forEach(function (button) {
            button.hidden = false;
            button.addEventListener('click', function () {
                if (unavailable(button)) return;
                go(targetIndex(button));
            });
        });
    }

    items.forEach(function (item, i) {
        item.link.addEventListener('click', function (e) {
            // Leave modified clicks to the browser so the link can still be opened or
            // copied as one.
            if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            e.preventDefault();
            go(i);
        });
    });

    /* A choice stands until the reader goes looking somewhere else themselves. Their
       input says so directly, but dragging the scrollbar, clicking its track and
       find-in-page produce no input events at all, so the page drifting away from where
       the choice parked also releases it. The parking position is recorded from the
       first scroll after the jump rather than at the jump, because the browser has not
       necessarily moved yet when a hash is assigned. */
    function release() {
        choose(-1);
    }

    function trackDrift() {
        if (chosen < 0) return;
        if (chosenAt === null) chosenAt = window.scrollY;
        else if (Math.abs(window.scrollY - chosenAt) > 4) release();
    }

    window.addEventListener('wheel', release, { passive: true });
    window.addEventListener('touchmove', release, { passive: true });

    var SCROLL_KEYS = /^(Arrow(Up|Down)|Page(Up|Down)|Home|End| )$/;

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeIndex(true);
        if (SCROLL_KEYS.test(e.key)) release();
    });

    document.addEventListener('click', function (e) {
        if (!nav.contains(e.target)) closeIndex(false);
    });

    // Covers arriving on a shared turn link and the back button. A hash naming something
    // that is not a user turn, or no hash at all, clears the choice rather than leaving
    // the last one standing.
    window.addEventListener('hashchange', function () {
        choose(indexForHash());
        update();
    });

    var queued = false;
    window.addEventListener(
        'scroll',
        function () {
            if (queued) return;
            queued = true;
            requestAnimationFrame(function () {
                queued = false;
                trackDrift();
                update();
            });
        },
        { passive: true }
    );

    choose(indexForHash());
    update();
})();
