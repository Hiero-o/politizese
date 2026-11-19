import HeaderDashboard from "@/components/HeaderDashboard";
import ChatAssistente from "@/components/Assistente/ChatAssistente";

export default function AssistentePage() {
  return (
    <>
      <HeaderDashboard />
      <main className="min-h-[calc(100vh-80px)] bg-[#141618] text-white">
        <ChatAssistente />
      </main>
    </>
  );
}
