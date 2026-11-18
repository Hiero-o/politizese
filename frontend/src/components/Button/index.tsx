
import { ReactNode } from "react"

interface ButtonProps {
    label?: string,
    hasLabel?: boolean,
    hasIcon?: boolean,
    icon?: ReactNode
}

export default function Button({ label, hasLabel, hasIcon, icon }: ButtonProps) {
    return (
        <>
            {hasLabel && (
                <button>{label}</button>
            )}
            {hasLabel === false && hasIcon === true && (
                <button className="w-[40px] h-[40px] shrink-0 flex items-center justify-center border border-[#51565c] p-[3px] rounded-[8px] hover:bg-[#2d3033] transition-[0.2s] cursor-pointer">
                    <div className="bg-[#2d3033] h-[30px] w-[30px] shrink-0 rounded-[4px] flex items-center justify-center">
                        {icon}
                    </div>
                </button>
            )}
        </>
    )
}
