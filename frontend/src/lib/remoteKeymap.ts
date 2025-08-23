export type RemoteEvent =
    | "remote:left"
    | "remote:right"
    | "remote:up"
    | "remote:down"
    | "remote:ok"
    | "remote:longpress:ok";

export function attachRemoteKeymap() {
    let okDownAt = 0;
    const onKeyDown = (e: KeyboardEvent) => {
        const key = e.key.toLowerCase();
        if (["arrowleft", "arrowright", "arrowup", "arrowdown", "enter"].includes(key)) {
            e.preventDefault();
        }
        if (key === "arrowleft") dispatch("remote:left");
        if (key === "arrowright") dispatch("remote:right");
        if (key === "arrowup") dispatch("remote:up");
        if (key === "arrowdown") dispatch("remote:down");
        if (key === "enter") {
            if (okDownAt === 0) okDownAt = Date.now();
            dispatch("remote:ok");
        }
    };
    const onKeyUp = (e: KeyboardEvent) => {
        const key = e.key.toLowerCase();
        if (key === "enter") {
            const held = Date.now() - okDownAt;
            okDownAt = 0;
            if (held >= 600) dispatch("remote:longpress:ok");
        }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
        window.removeEventListener("keydown", onKeyDown);
        window.removeEventListener("keyup", onKeyUp);
    };
}

function dispatch(name: RemoteEvent) {
    window.dispatchEvent(new CustomEvent(name));
}
