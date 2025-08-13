"use client";

import { useEffect } from "react";
import { Backdrop } from "@/components/tv/surfaces/Backdrop";
import { PrimaryStage } from "@/components/tv/surfaces/PrimaryStage";
import { SideRail } from "@/components/tv/surfaces/SideRail";
import { FooterRibbon } from "@/components/tv/surfaces/FooterRibbon";
import { AlertLayer } from "@/components/tv/layers/AlertLayer";
import { VibeSwitcher } from "@/components/tv/layers/VibeSwitcher";
import { QuietHoursBadge } from "@/components/tv/QuietHoursBadge";
import { attachRemoteKeymap } from "@/lib/remoteKeymap";
import { scheduler } from "@/services/scheduler";
import { wsHub } from "@/services/wsHub";
import { attachUiEffects } from "@/lib/uiEffects";

export default function TvLive() {
    useEffect(() => {
        const detach = attachRemoteKeymap();
        const onPrev = () => scheduler.nudge("prev");
        const onNext = () => scheduler.nudge("next");
        window.addEventListener("remote:left", onPrev);
        window.addEventListener("remote:right", onNext);
        wsHub.start();
        const detachUi = attachUiEffects();
        return () => { detachUi(); detach(); };
    }, []);
    return (
        <main className="min-h-screen bg-black text-white">
            <div className="relative min-h-screen">
                <Backdrop dim={0.35} blur={10} />
                <PrimaryStage />
                <SideRail />
                <FooterRibbon />
                <QuietHoursBadge />
                <VibeSwitcher />
                <AlertLayer />
            </div>
        </main>
    );
}


