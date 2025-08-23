"use client";

import { useEffect, useState } from "react";
import { useSceneManager } from "@/state/sceneManager";
import { AlertPanel } from "@/components/tv/widgets/AlertPanel";

export function AlertLayer() {
    const scene = useSceneManager();
    const [active, setActive] = useState(false);
    useEffect(() => {
        const onIncoming = () => { setActive(true); scene.toAlert("ws_alert"); };
        window.addEventListener("alert:incoming", onIncoming);
        return () => window.removeEventListener("alert:incoming", onIncoming);
    }, [scene]);
    if (!active && scene.scene !== "alert") return null;
    return <AlertPanel />;
}
