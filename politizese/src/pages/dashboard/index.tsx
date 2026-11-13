import HeaderDashboard from "../../components/HeaderDashboard"
import CardPostPreview from "@/components/CardPostPreview"

export default function Dashboard() {
    const posts = [
        {
            id: 1,
            tag: "Deputado Federal · Ricardo Almeida",
            title: "Projeto propõe ampliar investimentos na educação pública",
            hasImage: true,
            img: "https://picsum.photos/seed/educationnews/800/450",
            content: "Uma nova proposta apresentada na Câmara busca aumentar os investimentos destinados à infraestrutura das escolas públicas, com foco na modernização das salas de aula e na valorização dos profissionais da educação."
        },
        {
            id: 2,
            tag: "Vereadora · Mariana Costa",
            title: "Câmara discute novas medidas para melhorar o transporte público",
            hasImage: true,
            img: "https://picsum.photos/seed/transportnews/800/450",
            content: "A proposta prevê mudanças nas linhas de ônibus municipais, ampliação dos horários de funcionamento e melhorias na acessibilidade para passageiros com mobilidade reduzida."
        },
        {
            id: 3,
            tag: "Deputado Estadual · Felipe Martins",
            title: "Deputado apresenta projeto de incentivo ao primeiro emprego",
            hasImage: true,
            img: "https://picsum.photos/seed/employmentnews/800/450",
            content: "A iniciativa pretende criar incentivos para empresas que contratarem jovens em busca da primeira oportunidade profissional, oferecendo capacitação e acompanhamento durante os primeiros meses."
        },
        {
            id: 4,
            tag: "Vereador · Lucas Ferreira",
            title: "Novo programa pretende ampliar a iluminação pública nos bairros",
            hasImage: true,
            img: "https://picsum.photos/seed/citynews/800/450",
            content: "O projeto prevê a instalação de luminárias de LED em regiões com baixa iluminação, buscando melhorar a segurança e a qualidade de vida dos moradores."
        },
        {
            id: 5,
            tag: "Deputada Federal · Camila Rodrigues",
            title: "Proposta busca ampliar o acesso à saúde preventiva",
            hasImage: true,
            img: "https://picsum.photos/seed/healthnews/800/450",
            content: "A parlamentar apresentou uma iniciativa voltada à ampliação de campanhas de prevenção, exames periódicos e atendimento básico em comunidades com menor acesso aos serviços de saúde."
        },
        {
            id: 6,
            tag: "Vereadora · Beatriz Oliveira",
            title: "Projeto prevê revitalização de praças e espaços públicos",
            hasImage: true,
            img: "https://picsum.photos/seed/parknews/800/450",
            content: "A proposta busca recuperar áreas de convivência, instalar equipamentos de lazer e ampliar a arborização em diferentes regiões da cidade."
        },
    ]

    return (
        <>
            <HeaderDashboard />
            <main className="flex items-start justify-center flex-row min-h-[calc(70vh-80px)] ">
                <div className="min-h-full flex items-center justify-between w-[90%] max-w-[1200px] flex-col">
                    <div className="grid grid-cols-1 md:grid-cols-2 w-full md:[&>article:nth-child(odd)]:border-r md:[&>article:nth-child(odd)]:border-[#373a3e] gap-[10px] mt-[10px]">
                        {posts.map((post) => (
                            <CardPostPreview
                                key={post.id}
                                tag={post.tag}
                                title={post.title}
                                img={post.img}
                            />
                        ))}
                    </div>
                </div>
            </main>
        </>
    )
}