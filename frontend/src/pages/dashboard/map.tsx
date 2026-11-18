import dynamic from "next/dynamic";
import HeaderDashboard from "../../components/HeaderDashboard";

const MapDashboard = dynamic(() => import("../../components/MapDashboard"), 
    { ssr: false, loading: () => (
            <main className="flex min-h-[calc(100vh-80px)] items-center justify-center bg-[#111315] text-white">
                <p className="text-sm text-[#9ca3af]">Caregando mapa territorial...</p>
            </main>
        ),
    })

export default function MapPage() {
    return (
        <>
            <HeaderDashboard />
            <MapDashboard />
        </>
    )
}