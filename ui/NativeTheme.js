.pragma library
function luminance(value) {
    if (!/^#[0-9a-fA-F]{6}$/.test(value)) return -1;
    var values = [1,3,5].map(function(i) { var c = parseInt(value.slice(i,i+2),16)/255; return c <= 0.04045 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4); });
    return values[0]*0.2126 + values[1]*0.7152 + values[2]*0.0722;
}
function contrast(a,b) {
    var x=luminance(a), y=luminance(b);
    return x < 0 || y < 0 ? 0 : (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05);
}
function normalize(foreground,background,accent,font) {
    var fg=String(foreground), bg=String(background), ac=String(accent);
    if (contrast(fg,bg) < 4.5) { fg="#cacccc"; bg="#101315"; }
    if (contrast(ac,bg) < 4.5) ac=fg;
    return {foreground:fg,background:bg,accent:ac,fontFamily:typeof font === "string" && font.length ? font : "monospace"};
}
