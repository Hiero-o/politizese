import Button from "../Button"
import { TbPlus, TbLinkFilled  } from "react-icons/tb";
import { BiExpandAlt } from "react-icons/bi";

interface PostPreviewProps {
    title: string,
    tag: string,
    img: string
}

export default function CardPostPreview({ title, tag, img }: PostPreviewProps) {
    return (
        <article className="flex flex-row items-center justify-center p-[20px] border border-[#373a3e] w-full rounded-[8px]">
            <img className="h-[90px] w-[90px] mr-[10px] rounded-[4px]" src={img} alt={title} />
            <div className="flex flex-col items-start justify-center">
                <span className="text-[#008cff] text-[14px] leading-none mb-[10px]">{tag}</span>
                <h1 className="text-[25px] font-semibold leading-none line-clamp-2">{title}</h1>
            </div>
            <div className="ml-[20px] flex flex-col gap-[5px]">
                <Button hasLabel={false} hasIcon icon={<TbPlus />}/>
                <Button hasLabel={false} hasIcon icon={<BiExpandAlt />}/>
            </div>
        </article>
    )
}