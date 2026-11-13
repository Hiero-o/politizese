import { Inter } from "next/font/google";

interface ItemNavProps {
  label: string;
  link: string;
}

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
})

export default function ItemNav({ label, link }: ItemNavProps) {
  return (
    <a href={link} className={`${inter.className} font-normal text-[13px] rounded-[8px] transition-[0.2s] hover:text-[#dadada]`}>
      {label}
    </a>
  )
}