"use client";

import { useEffect } from "react";
import { wsHub } from "@/services/wsHub";

export default function WsBootstrap() {
    useEffect(() => {
        // Start only the music channel by default at app-level
        wsHub.start({ music: true, care: false });
        return () => wsHub.stop({ music: true, care: false });
    }, []);
    return null;
}


