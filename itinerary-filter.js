// Pure visibility rules for the itinerary page (also loaded by Node tests).
(function (root) {
    const SPECIAL_TYPE = 'Special Ticketed Event'; // showtime type used for after-hours party performances

    // A show is "special" if any of its showtimes is a ticketed-event performance
    // (e.g. Mickey's Very Merry Christmas Party). Those are only on party nights.
    const isSpecialShowtime = st => (st?.type || '') === SPECIAL_TYPE;

    // Special shows always display; everything else is hidden unless the toggle is on
    // or it is a non-meet show with at most maxTimes performances.
    function isVisible(show, includeAll, maxTimes) {
        if (show.special) return true;
        return includeAll || (!show.meet && show.times.length <= maxTimes);
    }

    const api = { SPECIAL_TYPE, isSpecialShowtime, isVisible };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.ItineraryFilter = api;
})(typeof self !== 'undefined' ? self : this);
