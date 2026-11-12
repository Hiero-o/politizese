import ItemNav from "../ItemNav";

export default function HeaderDashboard() {
  const NavigationItems = [
    {
      label: "Início",
      link: "/dashboard"
    },
    {
      label: "Seguindo",
      link: "/dashboard/following"
    },
    {
      label: "Novidades",
      link: "/dashboard/news"
    },
    {
      label: "Mapa",
      link: "/dashboard/map"
    },
    {
      label: "Configurações",
      link: "/dashboard/settings"
    },
  ]

  return (
    <header className="flex items-center justify-center h-[80px] sticky top-0 z-[999] transition-[0.2s] w-full bg-[#1a1b1c] border-b border-[#373a3e]">
      <div className="flex items-center justify-between max-w-[1200px] w-[90%] z-[999]">
        <article className="flex flex-row items-center justify-end">
          <img src="./imageuser2.png" alt="Image User" className="h-[40px] w-[40px] rounded-[8px] border border-[#3e4246] mr-[10px]"/>
          <div className="flex flex-col items-start justify-center">
            <h1 className="text-[14px]">Victor</h1>
            <p className="text-[12px] text-[#dadada]">victor@email.com</p>
          </div>
        </article>
        <nav className="flex gap-[25px]">
          {NavigationItems.map((i) => (
            <ItemNav label={i.label} link={i.link}/>
          ))}
        </nav>
      </div>
    </header>
  );
}
