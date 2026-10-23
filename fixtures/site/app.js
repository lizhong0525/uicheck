// Deliberate bugs for the UICheck demo:
console.error("analytics: failed to load tracker config");
// This throws an uncaught exception on page load:
window.tracker.track("pageview");
