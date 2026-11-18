
import Button from "../Button"
import { TbPlus } from "react-icons/tb"
import { BiExpandAlt } from "react-icons/bi"

interface PostPreviewProps {
    title: string,
    tag: string,
    img: string
}

export default function CardPostPreview({ title, tag, img }: PostPreviewProps) {
    return (
        <article className="flex justify-center flex-row items-stretch w-full border border-[#373a3e] rounded-[8px] overflow-hidden">
            <img className="w-[120px] shrink-0 object-cover" src={img} alt={title}/>
            <div className="flex flex-1 min-w-0 flex-col items-start justify-center p-[25px]">
                <span className="text-[#008cff] text-[14px] leading-none mb-[10px]">{tag}</span>
                <h1 className="text-[25px] font-semibold leading-none line-clamp-2">{title}</h1>
            </div>
            <div className="flex flex-col justify-center p-[12px] gap-[8px]">
                <Button hasLabel={false} hasIcon icon={<TbPlus />} />
                <Button hasLabel={false} hasIcon icon={<BiExpandAlt />} />
            </div>
        </article>
    )
}
