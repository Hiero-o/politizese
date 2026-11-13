import { ReactNode } from "react"

interface ButtonProps {
    label?: string,
    hasLabel?: boolean
    hasIcon?: boolean,
    icon?: ReactNode
}

export default function Button({ label, hasLabel, hasIcon, icon }: ButtonProps) {
    return (
        <>
            <button>
                {label}
            </button>
            {hasLabel === false && hasIcon === true && (
                <button className="border border-[#51565c] p-[3px] rounded-[8px] hover:bg-[#2d3033] transition-[0.2s] cursor-pointer">
                    <div className="bg-[#2d3033] h-[30px] w-[30px] rounded-[4px] flex items-center justify-center">
                        {icon}
                    </div>
                </button>
            )}
        </>
    )
}