/* Warmed tooltips for anything on the page carrying a title.
 *
 * A tooltip waits before appearing, so that sweeping the cursor across a row of turn
 * timestamps on the way somewhere else does not flash a dozen of them. But once the
 * reader has read one, they are reading tooltips, and making them wait again for each
 * neighbour is just lag. So the page stays warm briefly after one closes: the next opens
 * at once and skips its fade. The warmth is shared across every trigger, which is the
 * point, since the ones worth reading in a row sit side by side.
 *
 * The text stays in the markup as a real title attribute and is only moved aside here,
 * so without this script the browser's own tooltips still work.
 */
(function () {
    // A pointer that cannot hover has no use for any of this, and holding a touch would
    // only leave a tooltip stranded with no way to dismiss it.
    if (!window.matchMedia('(hover: hover)').matches) return;

    var OPEN_DELAY = 200;
    var WARM_FOR = 300;
    var GAP = 6;
    var EDGE = 4;

    var triggers = document.querySelectorAll('[title]');
    if (!triggers.length) return;

    var tip = document.createElement('div');
    tip.className = 'tooltip';
    tip.id = 'sb-tooltip';
    // role="tooltip" plus aria-describedby on whichever trigger is showing. The text is
    // cleared on hide as well, because opacity does not take an element out of the
    // accessibility tree and a stray description would be left sitting in the document.
    tip.setAttribute('role', 'tooltip');
    document.body.appendChild(tip);

    triggers.forEach(function (el) {
        el.setAttribute('data-tip', el.getAttribute('title'));
        el.removeAttribute('title');
    });

    var shownFor = null;
    var pendingFor = null;
    var openTimer = null;
    var coolTimer = null;
    var warm = false;

    function place(trigger) {
        var at = trigger.getBoundingClientRect();
        var width = tip.offsetWidth;
        var height = tip.offsetHeight;
        var left = at.left + at.width / 2 - width / 2;
        var limit = document.documentElement.clientWidth - width - EDGE;
        var top = at.bottom + GAP;
        // Near the foot of the window there is no room underneath, so it goes above.
        if (top + height + EDGE > window.innerHeight) top = at.top - height - GAP;
        tip.style.left = Math.round(Math.max(EDGE, Math.min(left, limit))) + 'px';
        tip.style.top = Math.round(Math.max(EDGE, top)) + 'px';
    }

    function show(trigger) {
        window.clearTimeout(coolTimer);
        pendingFor = null;
        tip.textContent = trigger.getAttribute('data-tip');
        tip.setAttribute('data-instant', warm ? 'true' : 'false');
        // Measured at the origin, so a previous position cannot skew the width.
        tip.style.left = '0px';
        tip.style.top = '0px';
        place(trigger);
        tip.setAttribute('data-show', 'true');
        trigger.setAttribute('aria-describedby', tip.id);
        shownFor = trigger;
        warm = true;
    }

    function hide() {
        window.clearTimeout(openTimer);
        pendingFor = null;
        if (!shownFor) return;
        tip.setAttribute('data-show', 'false');
        shownFor.removeAttribute('aria-describedby');
        tip.textContent = '';
        shownFor = null;
        // Only a tooltip that actually opened leaves the page warm behind it.
        window.clearTimeout(coolTimer);
        coolTimer = window.setTimeout(function () {
            warm = false;
        }, WARM_FOR);
    }

    function arm(trigger) {
        // mouseover repeats as the cursor travels within a trigger; without this the
        // timer would restart on every one and the tooltip would never open.
        if (trigger === shownFor || trigger === pendingFor) return;
        window.clearTimeout(openTimer);
        if (warm) {
            show(trigger);
        } else {
            pendingFor = trigger;
            openTimer = window.setTimeout(function () {
                show(trigger);
            }, OPEN_DELAY);
        }
    }

    function triggerFor(node) {
        return node && node.closest ? node.closest('[data-tip]') : null;
    }

    // Delegated: a long transcript carries hundreds of triggers, and the turn bodies can
    // nest one inside another, where closest() picks the innermost.
    document.addEventListener('mouseover', function (e) {
        var trigger = triggerFor(e.target);
        if (trigger) arm(trigger);
        else hide();
    });

    document.addEventListener('mouseleave', hide);

    // Reaching a control by keyboard is deliberate, so it needs no warming up.
    document.addEventListener('focusin', function (e) {
        var trigger = triggerFor(e.target);
        if (trigger) show(trigger);
    });

    document.addEventListener('focusout', hide);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') hide();
    });

    // The tooltip is positioned against the window, so it has to be brought along when
    // the page moves. Hiding instead would be wrong for a trigger inside the sticky
    // header, which does not move at all: clicking a stepper scrolls the page while the
    // cursor stays on the button it just pressed.
    function reflow() {
        if (!shownFor) return;
        var at = shownFor.getBoundingClientRect();
        if (at.bottom < 0 || at.top > window.innerHeight) hide();
        else place(shownFor);
    }

    var queued = false;
    function onMove() {
        if (queued) return;
        queued = true;
        requestAnimationFrame(function () {
            queued = false;
            reflow();
        });
    }

    window.addEventListener('scroll', onMove, { passive: true });
    window.addEventListener('resize', onMove);

    // Opening a tool call or the turn navigator moves the page out from under it too.
    // toggle does not bubble, hence the capture.
    document.addEventListener('toggle', hide, true);
})();
