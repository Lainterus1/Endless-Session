.pragma library
.import "StreamModel.js" as Model

function validTheme(value) {
        return Model.object(value) && ["foreground", "background", "accent"].every(function(k) {
            return typeof value[k] === "string" && /^#[0-9a-fA-F]{6}$/.test(value[k]);
        }) && typeof value.fontFamily === "string" && value.fontFamily.length > 0;
    }
function apply(cache, needsReset, lastSequence, line) {
        var frame;
        try { frame = JSON.parse(line); } catch (e) { return {invalid:true}; }
        if (!Model.object(frame) || !Array.isArray(frame.chats) || !Model.integer(frame.sequence)
            || frame.schema_version !== 1 || ["ready", "scanning", "unknown"].indexOf(frame.discovery) < 0
            || !Model.integer(frame.unknown_count) || frame.unknown_count < 0 || !validTheme(frame.theme)) { return {invalid:true}; }
        if (frame.sequence <= lastSequence) return {stale:true};
        var seen = {};
        var valid = frame.chats.every(function(chat) {
            if (!Model.object(chat) || typeof chat.thread_id !== "string" || !/^[0-9a-f-]{36}$/.test(chat.thread_id)
                || seen[chat.thread_id]) return false;
            seen[chat.thread_id] = true;
            if (!Model.validFrame({schema_version: 1, sequence: frame.sequence, chats: [chat]}, chat.thread_id)) return false;
            var old = cache[chat.thread_id];
            return chat.reset || (!needsReset && old && old.source_epoch === chat.source_epoch);
        });
        if (!valid) { return {invalid:true}; }
        var next = {};
        frame.chats.forEach(function(chat) {
            var items = chat.reset ? [] : cache[chat.thread_id].items.slice();
            chat.items.forEach(function(item) {
                var index = items.findIndex(function(old) { return old.id === item.id; });
                if (index >= 0) items[index] = item; else items.push(item);
            });
            next[chat.thread_id] = Object.assign({}, chat, {items: items.slice(-8), reset: true});
        });
        return {frame:frame,cache:next,monitored:frame.chats.map(function(chat) {
            return {thread_id:chat.thread_id,status:chat.status,pending_questions:chat.pending_questions};
        }).sort(function(a,b) { return a.thread_id.localeCompare(b.thread_id); })};
}
