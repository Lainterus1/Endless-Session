.pragma library

function decide(chats, discovery, now, previous) {
    var starts = {}, active = false, allIdle = chats.length > 0;
    function uncertain(key) {
        var old = previous[key];
        starts[key] = typeof old === "number" && old <= now ? old : now;
    }
    if (discovery !== "ready") uncertain("discovery");
    chats.forEach(function(chat) {
        var known = ["working", "waiting_input", "idle"].indexOf(chat.status) >= 0;
        if (!known) uncertain("chat:" + chat.thread_id);
        if (known && (chat.status === "working" || chat.status === "waiting_input" || chat.pending_questions > 0)) active = true;
        if (chat.status !== "idle" || chat.pending_questions !== 0) allIdle = false;
    });
    var errors = Object.keys(starts);
    var grace = errors.some(function(key) { return now - starts[key] < 300000; });
    return {starts: starts, hold: active || grace, reason: active ? "active" : grace ? "uncertainty_grace" : errors.length ? "loss_timeout" : chats.length ? "all_completed" : "empty",
        all_completed: discovery === "ready" && allIdle && !errors.length, uncertain: errors.length > 0};
}
