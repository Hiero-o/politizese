
import { useEffect, useState } from "react";
import L from "leaflet";
import {
    GeoJSON,
    MapContainer,
    TileLayer,
    Pane,
    useMap,
} from "react-leaflet";
import type { PathOptions } from "leaflet";
import type {
    Feature,
    FeatureCollection,
    Geometry,
    GeoJsonProperties,
} from "geojson"

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "")
const CARTO_API_KEY = process.env.NEXT_PUBLIC_CARTO_API_KEY;

type MapCollection = FeatureCollection<
    Geometry,
    GeoJsonProperties
>

interface MapLayer {
    id: string;
    name: string;
    description: string;
    category: string;
    geometry: string;
    available: boolean;
    endpoint: string | null;
}

interface LayerCatalogResponse {
    total: number;
    available: number;
    layers: MapLayer[];
}

interface LayerData {
    [layerId: string]: MapCollection;
}

interface LayerErrors {
    [layerId: string]: string;
}

const GROUPS = [
    {
        id: "infraestrutura",
        title: "Infraestrutura",
        description: "Obras e intervenções públicas",
    },
    {
        id: "risco_ambiental",
        title: "Áreas de risco",
        description: "Áreas territorialmente mapeadas",
    },
    {
        id: "ocorrencias",
        title: "Ocorrências",
        description: "Eventos registrados pela Prefeitura",
    },
]

function getRiskColor(value: unknown): string {
    const classification = String(value ?? "").trim().toUpperCase()

    switch (classification) {
        case "R1":
            return "#22c55e";

        case "R2":
            return "#eab308";

        case "R3":
            return "#f97316";

        case "R4":
            return "#ef4444";

        case "AREA ENCERRADA":
            return "#64748b";

        case "AREA EM MONITORAMENTO":
            return "#a78bfa";

        default:
            return "#94a3b8";
    }
}

function getPolygonStyle( layerId: string, properties: GeoJsonProperties ): PathOptions {
    const data = properties ?? {}
    let color = "#94a3b8"

    if (layerId === "risco_geologico") {
        color = getRiskColor(
            data.tx_grau_de_risco_geologico
        )
    }

    if (layerId === "risco_hidrologico") {
        color = getRiskColor(
            data.tx_grau_risco_hidrologico
        )
    }

    return {
        color,
        weight: 1.5,
        opacity: 0.9,
        fillColor: color,
        fillOpacity: 0.3,
    }
}

function getPointColor( layerId: string, properties: GeoJsonProperties ): string {
    const data = properties ?? {}

    if (layerId === "obras") {
        const status = String(data.status ?? data.situacao ?? "" ).toUpperCase()

        if (status.includes("CONCLU")) {
            return "#22c55e"
        }

        if (status.includes("SUSPEN")) {
            return "#94a3b8"
        }

        return "#38bdf8"
    }

    const colors: Record<string, string> = {
        alagamentos: "#60a5fa",
        inundacoes: "#22d3ee",
        deslizamentos: "#fb923c",
        quedas_arvores: "#a3e635",
    }

    return colors[layerId] ?? "#e2e8f0"
}

const PROPERTY_LABELS: Record<string, string> = {
    cd_identificador: "Identificador",
    dt_ocorrencia: "Data da ocorrência",
    dc_tipo_ocorrencia: "Tipo de ocorrência",
    dt_carga: "Data de atualização",
    nm_distrito: "Distrito",
    nm_subprefeitura: "Subprefeitura",

    nm_area_risco: "Área de risco",
    tx_grau_de_risco_geologico: "Grau de risco geológico",
    tx_grau_risco_hidrologico: "Grau de risco hidrológico",

    sg_area_risco: "Código da área",
    sg_setor_risco: "Setor",
    tx_tipo_processo_geologico: "Processo geológico",

    dt_vistoria: "Data da vistoria",
    dt_atualizacao: "Atualização",
    qt_moradia: "Moradias estimadas",

    status: "Situação",
    endereco: "Endereço",
    nome: "Nome",
    valor_contrato: "Valor do contrato",
    categoria: "Categoria",

    data_inicio: "Data de início",
    data_termino_prevista: "Término previsto",

    secretaria_contratante: "Secretaria contratante",
    secretaria_responsavel: "Secretaria responsável",
    regiao: "Região",
    subprefeitura: "Subprefeitura",
    nome_obra: "Nome da obra",
    codigo_obra: "Código da obra",
    processo: "Processo",
    escopo_contrato: "Escopo do contrato",
    origem_dados: "Origem dos dados",
    situacao: "Situação",
}

function escapeHtml(value: string): string {
    return value.replace(/[&<>"']/g, (character) => {
        const entities: Record<string, string> = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;",
        }

        return entities[character]
    })
}

function formatDateValue(value: string): string {
    const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})Z?$/)

    if (dateOnly) {
        const [, year, month, day] = dateOnly;

        return `${day}/${month}/${year}`;
    }

    const parsedDate = new Date(value)

    if (Number.isNaN(parsedDate.getTime())) {
        return value
    }

    const hasTime = value.includes("T")

    return new Intl.DateTimeFormat("pt-BR", {
        timeZone: "America/Sao_Paulo",
        dateStyle: "short",
        ...(hasTime ? { timeStyle: "short" as const } : {}),
    }).format(parsedDate)
}

function formatPropertyValue( value: unknown, key: string ): string {
    if (value === null || value === undefined) {
        return "Não informado"
    }
    if (
        typeof value === "string" &&
        (
            key.startsWith("dt_") ||
            key.toLowerCase().includes("data")
        )
    ) {
        return formatDateValue(value)
    }

    if (typeof value === "object") {
        return JSON.stringify(value)
    }

    return String(value)
}

function formatCurrencyValue(value: unknown): string {
    if (value === null || value === undefined || value === "") {
        return "Não informado"
    }

    if (typeof value === "number") {
        return new Intl.NumberFormat("pt-BR", {
            style: "currency",
            currency: "BRL",
        }).format(value)
    }

    const raw = String(value).trim()

    if (/R\$/i.test(raw)) {
        return raw
    }

    let normalized = raw.replace(/\s/g, "")

    if (normalized.includes(",") && normalized.includes(".")) {
        normalized = normalized.replace(/\./g, "").replace(",", ".");
    } else if (normalized.includes(",")) {
        normalized = normalized.replace(",", ".")
    }

    const numericValue = Number(normalized)

    if (!Number.isFinite(numericValue)) {
        return raw;
    }

    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(numericValue)
}

function getPropertyLabel(key: string): string {
    return (
        PROPERTY_LABELS[key] ??
        key
            .replace(/_/g, " ")
            .replace(/\b\w/g, (character) => character.toUpperCase())
    )
}

function createPopupHtml( properties: GeoJsonProperties ): string {
    const data = properties ?? {}

    const title =
        data.nm_area_risco ??
        data.nome ??
        data.name ??
        data.dc_tipo_ocorrencia ??
        "Detalhes do registro"

    const priorityKeys = [
        "data_inicio",
        "data_termino_prevista",
        "dt_ocorrencia",
        "dt_vistoria",
        "dt_atualizacao",
        "dt_carga",
    ]

    const entries = Object.entries(data)
        .filter(
            ([, value]) =>
                value !== null &&
                value !== undefined &&
                value !== ""
        )
        .sort(([keyA], [keyB]) => {
            const indexA = priorityKeys.indexOf(keyA);
            const indexB = priorityKeys.indexOf(keyB);
            const priorityA = indexA === -1 ? Infinity : indexA;
            const priorityB = indexB === -1 ? Infinity : indexB;

            return priorityA - priorityB;
        })
        .slice(0, 14)

    const rows = entries.map(([key, value]) => {
        return `
      <div class="map-popup-row">
        <dt>${escapeHtml(getPropertyLabel(key))}</dt>
        <dd>${escapeHtml(formatPropertyValue(value, key))}</dd>
      </div>
    `;
    }).join("")

    return `
    <div class="map-popup">
      <h3>${escapeHtml(formatPropertyValue(title, "nome"))}</h3>
      <dl class="map-popup-rows">
        ${rows}
      </dl>
    </div>
  `
}

function createWorkSummaryHtml( properties: GeoJsonProperties ): string {
    const data = properties ?? {};
    const title = data.nome_obra ?? "Obra pública";
    const status = data.status ?? data.situacao;
    const valueKey =
        Object.keys(data).find(
            (key) =>
                /(valor|vlr)/i.test(key) &&
                /(contrato|obra|total)/i.test(key)
        ) ??
        Object.keys(data).find(
            (key) => /(valor|vlr)/i.test(key)
        )

    const fields = [
        ["Data de início", "data_inicio"],
        ["Término previsto", "data_termino_prevista"],
        ["Valor da obra", valueKey ?? "__valor_nao_encontrado__"],
        ["Secretaria contratante", "secretaria_contratante"],
        ["Região", "regiao"],
        ["Subprefeitura", "subprefeitura"],
        ["Endereço", "endereco"],
        ["Categoria", "categoria"],
    ] as const

    const rows = fields.map(([label, key]) => {
        const value =
            key === valueKey
                ? formatCurrencyValue(data[key])
                : key === "__valor_nao_encontrado__"
                    ? "Não informado"
                    : formatPropertyValue(data[key], key);

        return `
      <div class="map-popup-row ${key === valueKey ? "map-popup-value" : ""}">
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value)}</dd>
      </div>
    `;
    }).join("")

    const statusHtml =
        status !== null && status !== undefined && status !== ""
            ? `
        <span class="map-popup-status">
          ${escapeHtml(formatPropertyValue(status, "status"))}
        </span>
      `
            : ""

    return `
    <div class="map-popup map-popup-summary">

      <div class="map-popup-header">
        <h3>${escapeHtml(formatPropertyValue(title, "nome_obra"))}</h3>

        <button
          type="button"
          class="map-popup-action"
          data-popup-action="details"
        >
          Detalhes →
        </button>
      </div>

      ${statusHtml}

      <dl class="map-popup-rows">
        ${rows}
      </dl>

    </div>
  `
}

function createWorkDetailsHtml( properties: GeoJsonProperties ): string {
    const data = properties ?? {}
    const entries = Object.entries(data).filter(([, value]) => value !== null && value !== undefined && value !== "")
    const rows = entries.map(([key, value]) => {
        return `
      <div class="map-popup-row">
        <dt>${escapeHtml(getPropertyLabel(key))}</dt>
        <dd>${escapeHtml(formatPropertyValue(value, key))}</dd>
      </div>
    `
    }).join("")

    return `
    <div class="map-popup map-popup-details">

      <div class="map-popup-header">

        <h3>Detalhes da obra</h3>

        <button
          type="button"
          class="map-popup-action"
          data-popup-action="summary"
        >
          ← Resumo
        </button>

      </div>

      <dl class="map-popup-rows">
        ${rows}
      </dl>

    </div>
  `
}

interface ViewportInfo {
    zoom: number;
    visiblePoints: number;
}

interface MapViewportObserverProps {
    layers: MapLayer[];
    layerData: LayerData;
    activeLayerIds: string[];
    onChange: (info: ViewportInfo) => void;
}

function MapViewportObserver({ layers, layerData, activeLayerIds, onChange, }: MapViewportObserverProps) {
    const map = useMap()

    useEffect(() => {
        function updateViewport() {
            const bounds = map.getBounds()

            let visiblePoints = 0

            for (const layerId of activeLayerIds) {
                const config = layers.find((layer) => layer.id === layerId)

                if (config?.geometry !== "Point") {
                    continue
                }

                const features = layerData[layerId]?.features ?? []

                for (const feature of features) {
                    if (feature.geometry?.type !== "Point") {
                        continue
                    }

                    const [longitude, latitude] =
                        feature.geometry.coordinates;

                    if (
                        Number.isFinite(longitude) &&
                        Number.isFinite(latitude) &&
                        bounds.contains([latitude, longitude])
                    ) {
                        visiblePoints++;
                    }
                }
            }

            onChange({
                zoom: map.getZoom(),
                visiblePoints,
            })
        }

        updateViewport()

        map.on("moveend", updateViewport)
        map.on("zoomend", updateViewport)

        return () => {
            map.off("moveend", updateViewport)
            map.off("zoomend", updateViewport)
        }

    }, [
        map,
        layers,
        layerData,
        activeLayerIds,
        onChange,
    ])

    return null
}

export default function MapDashboard() {
    const [layers, setLayers] = useState<MapLayer[]>([])
    const [layerData, setLayerData] = useState<LayerData>({})
    const [activeLayerIds, setActiveLayerIds] = useState<string[]>([])
    const [loadingLayerIds, setLoadingLayerIds] = useState<string[]>([])
    const [layerErrors, setLayerErrors] = useState<LayerErrors>({})
    const [catalogLoading, setCatalogLoading] = useState(true)
    const [catalogError, setCatalogError] = useState<string | null>(null)
    const showWorksLegend = activeLayerIds.includes("obras")
    const showRiskLegend = activeLayerIds.some((id) => ["risco_geologico", "risco_hidrologico"].includes(id))
    const showGeologicalSpecialLegend = activeLayerIds.includes("risco_geologico")
    const [viewportInfo, setViewportInfo] = useState<ViewportInfo>({ zoom: 11, visiblePoints: 0, })
    const enlargePoints = viewportInfo.zoom >= 15 && viewportInfo.visiblePoints > 0 && viewportInfo.visiblePoints <= 25

    useEffect(() => {
        let cancelled = false

        async function loadCatalog() {
            try {
                setCatalogLoading(true)

                const response = await fetch(`${API_BASE_URL}/api/map/layers`)

                if (!response.ok) {
                    throw new Error(
                        `Erro ao consultar a API: ${response.status}`
                    )
                }

                const result: LayerCatalogResponse = await response.json()

                if (!cancelled) {
                    setLayers(result.layers)
                    setCatalogError(null)
                }

            } catch (error) {
                if (!cancelled) {
                    setCatalogError(
                        error instanceof Error
                            ? error.message
                            : "Não foi possível conectar à API."
                    )
                }

            } finally {
                if (!cancelled) {
                    setCatalogLoading(false)
                }
            }
        }

        void loadCatalog()

        return () => {
            cancelled = true;
        }
    }, [])

    async function toggleLayer(layer: MapLayer) {

        const isActive = activeLayerIds.includes(layer.id)

        if (isActive) {
            setActiveLayerIds((current) =>
                current.filter((id) => id !== layer.id)
            )

            return
        }

        if (!layer.available || !layer.endpoint) {
            return
        }

        setActiveLayerIds((current) =>
            current.includes(layer.id)
                ? current
                : [...current, layer.id]
        )

        if (layerData[layer.id]) {
            return
        }

        if (loadingLayerIds.includes(layer.id)) {
            return
        }

        setLoadingLayerIds((current) => [
            ...current,
            layer.id,
        ])

        setLayerErrors((current) => {
            const updated = { ...current };
            delete updated[layer.id];
            return updated;
        })

        try {
            const response = await fetch(`${API_BASE_URL}${layer.endpoint}`)

            if (!response.ok) {
                throw new Error(
                    `Erro HTTP ${response.status}`
                )
            }

            const data: MapCollection = await response.json()

            if (
                data.type !== "FeatureCollection" ||
                !Array.isArray(data.features)
            ) {
                throw new Error(
                    "O servidor não retornou um GeoJSON válido."
                )
            }

            setLayerData((current) => ({
                ...current,
                [layer.id]: data,
            }))

        } catch (error) {
            setActiveLayerIds((current) =>
                current.filter((id) => id !== layer.id)
            )

            setLayerErrors((current) => ({
                ...current,
                [layer.id]:
                    error instanceof Error
                        ? error.message
                        : "Erro ao carregar os dados.",
            }))

        } finally {
            setLoadingLayerIds((current) =>
                current.filter((id) => id !== layer.id)
            )
        }
    }

    const loadedFeatureCount = Object.values(layerData).reduce((total, collection) => total + collection.features.length, 0)
    const availableLayers = layers.filter((layer) => layer.available).length

    return (
        <main className="text-white">
            <div className="mx-auto flex w-[90%] max-w-[1200px] flex-col gap-5 py-6">
                <section className="w-full flex flex-col justify-between gap-4 md:flex-row md:items-center">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Mapa territorial</h1>
                        <p className="mt-1 text-sm text-[#9ca3af]">Explore informações públicas e indicadores territoriais de São Paulo.</p>
                    </div>
                    <div className="flex flex-wrap gap-3 items-end justify-end w-full md:w-auto">
                        <div className="rounded-[8px] border border-[#373a3e] bg-[#1a1b1c] px-4 py-3 w-full md:w-auto">
                            <p className="text-xs text-[#9ca3af]">Camadas disponíveis</p>
                            <p className="mt-1 text-lg font-semibold">{catalogLoading ? "..." : `${availableLayers}/${layers.length}`}</p>
                        </div>
                        <div className="rounded-[8px] border border-[#373a3e] bg-[#1a1b1c] px-4 py-3 w-full md:w-auto">
                            <p className="text-xs text-[#9ca3af]">Registros carregados</p>
                            <p className="mt-1 text-lg font-semibold">{loadedFeatureCount.toLocaleString("pt-BR")}</p>
                        </div>
                    </div>
                </section>
                <section className="grid grid-cols-1 gap-4  xl:grid-cols-[320px_minmax(0,1fr)]">
                    <aside className="overflow-y-auto rounded-[8px] border border-[#373a3e] bg-[#1a1b1c] p-5">
                        <div className="mb-[18px]">
                            <div className="flex items-center justify-between">
                                <h2 className="text-base font-semibold">Camadas do mapa</h2>
                                <span className="rounded-[8px] bg-[#292d30] px-2 py-1 text-xs text-[#d1d5db]">{activeLayerIds.length} ativa(s)</span>
                            </div>
                            <p className="mt-2 text-xs leading-5 text-[#9ca3af]"> Selecione as informações que deseja visualizar no mapa.</p>
                        </div>

                        {catalogLoading && (
                            <p className="text-sm text-[#9ca3af]">Consultando camadas disponíveis...</p>
                        )}

                        {catalogError && (
                            <div role="alert" className="rounded-[8px] border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300 mb-[18px]">
                                Não foi possível conectar ao backend.
                                <p className="mt-1">{catalogError}</p>
                            </div>
                        )}

                        {!catalogLoading && !catalogError && GROUPS.map((group) => {
                            const groupLayers = layers.filter((layer) => layer.category === group.id)

                            return (
                                <div key={group.id} className="mb-6">
                                    <div className="mb-3 border-b border-[#373a3e] pb-2">
                                        <h3 className="text-sm font-semibold">{group.title}</h3>
                                        <p className="mt-1 text-[11px] text-[#8b9299]">{group.description}</p>
                                    </div>
                                    <div className="flex flex-col gap-2">
                                        {groupLayers.map((layer) => {

                                            const isActive = activeLayerIds.includes(layer.id);
                                            const isLoading =  loadingLayerIds.includes(layer.id);
                                            const isAvailable = layer.available;
                                            const featureCount = layerData[layer.id]?.features.length;

                                            return (
                                                <label key={layer.id}  className={`flex cursor-pointer items-start gap-3 rounded-[8px] border p-3 transition-colors ${isActive ? "border-cyan-500/40 bg-cyan-500/10" : "border-transparent bg-[#222528] hover:border-[#454b50]"} ${!isAvailable ? "cursor-not-allowed opacity-40" : ""} `}>
                                                    <input type="checkbox" checked={isActive} disabled={!isAvailable || isLoading} onChange={() => {void toggleLayer(layer)}} className="mt-1 h-4 w-4 shrink-0 accent-cyan-400"/>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex items-center justify-between gap-2">
                                                            <span className="text-xs font-medium text-[#f3f4f6]">{layer.name}</span>
                                                            {isLoading && (
                                                                <span className="text-[10px] text-cyan-300">Carregando...</span>
                                                            )}
                                                        </div>
                                                        <p className="mt-1 text-[10px] leading-4 text-[#9ca3af]">{layer.description}</p>
                                                        {featureCount !== undefined && (
                                                            <p className="mt-2 text-[10px] text-cyan-300">{featureCount.toLocaleString("pt-BR")} registros carregados</p>
                                                        )}
                                                        {!isAvailable && (
                                                            <p className="mt-1 text-[10px] text-red-300">Arquivo indisponível</p>
                                                        )}
                                                        {layerErrors[layer.id] && (
                                                            <p role="alert" className="mt-2 text-[10px] text-red-400">{layerErrors[layer.id]}</p>
                                                        )}
                                                    </div>
                                                </label>
                                            )
                                        })}
                                    </div>
                                </div>
                            )
                        })}
                        <div className="border-t border-[#373a3e] pt-4">
                            <h3 className="mb-3 text-xs font-semibold text-[#e5e7eb]">Legenda de risco</h3>
                            <div className="flex flex-col gap-2">
                                {[
                                    { label: "R1 — Baixo", color: "#22c55e" },
                                    { label: "R2 — Médio", color: "#eab308" },
                                    { label: "R3 — Alto", color: "#f97316" },
                                    { label: "R4 — Muito alto", color: "#ef4444" },
                                    { label: "Encerrado", color: "#64748b" },
                                    { label: "Em monitoramento", color: "#a78bfa" },
                                ].map((item) => (
                                    <div key={item.label} className="flex items-center gap-2">
                                        <span className="h-3 w-3 rounded-[8px]" style={{ backgroundColor: item.color }}/>
                                        <span className="text-[11px] text-[#b8bec4]">{item.label}</span>
                                    </div>
                                ))}
                            </div>
                            <p className="mt-4 text-[10px] leading-4 text-[#777f87]">As classificações e informações exibidas correspondem aos atributos das fontes oficiais disponibilizadas.</p>
                        </div>
                    </aside>
                    <div className="politizese-map relative h-[560px] overflow-hidden rounded-[8px] border border-[#373a3e] bg-[#171a1d] xl:h-full">
                        <MapContainer
                            center={[-23.5505, -46.6333]}
                            zoom={11}
                            minZoom={8}
                            maxZoom={19}
                            scrollWheelZoom={true}
                            className="h-full w-full"
                        >
                            <TileLayer
                                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                                url={`https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?key=${CARTO_API_KEY ?? ""}`}
                                subdomains="abcd"
                                maxZoom={20}
                            />
                            <Pane
                                name="labels"
                                style={{
                                    zIndex: 650,
                                    pointerEvents: "none",
                                }}
                            >
                                <TileLayer
                                    pane="labels"
                                    url={`https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png?key=${CARTO_API_KEY ?? ""}`}
                                    subdomains="abcd"
                                    maxZoom={20}
                                />
                            </Pane>

                            <MapViewportObserver
                                layers={layers}
                                layerData={layerData}
                                activeLayerIds={activeLayerIds}
                                onChange={setViewportInfo}
                            />

                            {activeLayerIds.map((layerId) => {

                                const layer = layers.find((item) => item.id === layerId)
                                const data = layerData[layerId]

                                if (!layer || !data) {
                                    return null;
                                }

                                return (
                                    <GeoJSON
                                        key={`${layerId}-${layer.geometry === "Point" && enlargePoints ? "large" : "normal"}`}
                                        data={data}
                                        style={(feature) => {
                                            const properties = feature?.properties ?? null;

                                            if (layer.geometry === "Point") {
                                                const color = getPointColor(layerId, properties)

                                                return {
                                                    color: "#ffffff",
                                                    weight: 1.2,
                                                    opacity: 0.95,
                                                    fillColor: color,
                                                    fillOpacity: 0.95,
                                                }
                                            }

                                            return getPolygonStyle(layerId, properties)
                                        }}


                                        pointToLayer={(feature, latlng) => {

                                            const color = getPointColor(layerId, feature.properties)

                                            const radius = enlargePoints
                                                ? 9 : layerId === "obras" ? 4 : 5

                                            return L.circleMarker(latlng, {
                                                radius,
                                                color: "#ffffff",
                                                weight: 1.2,
                                                opacity: 0.95,
                                                fillColor: color,
                                                fillOpacity: 0.95,
                                            })
                                        }}

                                        onEachFeature={(feature, leafletLayer) => {

                                            const properties = feature.properties ?? null;

                                            if (layerId === "obras") {

                                                leafletLayer.bindPopup(
                                                    createWorkSummaryHtml(properties),
                                                    {
                                                        maxWidth: 360,
                                                        maxHeight: 460,
                                                        className: "politizese-feature-popup",
                                                    }
                                                )

                                                leafletLayer.on("popupopen", (event) => {

                                                    const popup = event.popup
                                                    const popupElement = popup.getElement()

                                                    if (!popupElement) {
                                                        return
                                                    }

                                                    popupElement.onclick = (clickEvent: MouseEvent) => {

                                                        const target = clickEvent.target;

                                                        if (!(target instanceof Element)) {
                                                            return
                                                        }

                                                        const button = target.closest<HTMLButtonElement>("[data-popup-action]")

                                                        if (!button) {
                                                            return
                                                        }

                                                        clickEvent.preventDefault()
                                                        clickEvent.stopPropagation()

                                                        const action = button.dataset.popupAction;

                                                        if (action === "details") {
                                                            popup.setContent(createWorkDetailsHtml(properties))

                                                            popup.update()
                                                        } else if (action === "summary") {
                                                            popup.setContent(createWorkSummaryHtml(properties))
                                                            popup.update()
                                                        }
                                                    }
                                                })
                                            } else {
                                                leafletLayer.bindPopup(createPopupHtml(properties))
                                            }
                                        }}
                                    />
                                )
                            })}
                        </MapContainer>
                        {(showWorksLegend || showRiskLegend) && (
                            <div className="pointer-events-none absolute right-4 top-4 z-[700] max-h-[calc(100%-2rem)] w-[215px] overflow-y-auto rounded-[8px] border border-slate-300 bg-white/95 p-4 text-slate-800 shadow-lg backdrop-blur-sm">
                                <h3 className="mb-3 text-xs font-bold uppercase tracking-wider">Legenda do mapa</h3>
                                {showWorksLegend && (
                                    <section className="mb-4">
                                        <h4 className="mb-2 text-xs font-semibold">Obras públicas</h4>
                                        <div className="flex flex-col gap-2">
                                            {[
                                                {
                                                    label: "Concluída",
                                                    color: "#22c55e",
                                                },
                                                {
                                                    label: "Em andamento",
                                                    color: "#38bdf8",
                                                },
                                                {
                                                    label: "Suspensa",
                                                    color: "#94a3b8",
                                                },
                                            ].map((item) => (
                                                <div key={item.label} className="flex items-center gap-2">
                                                    <span className="h-3 w-3 rounded-full border border-black/10"
                                                        style={{
                                                            backgroundColor: item.color,
                                                        }}
                                                    />
                                                    <span className="text-[11px]">{item.label}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </section>
                                )}
                                {showRiskLegend && (
                                    <section className={showWorksLegend ? "border-t border-slate-200 pt-3" : ""}>
                                        <h4 className="mb-2 text-xs font-semibold">Classificação de risco</h4>
                                        <div className="flex flex-col gap-2">
                                            {[
                                                {
                                                    label: "R1 — Baixo",
                                                    color: "#22c55e",
                                                },
                                                {
                                                    label: "R2 — Médio",
                                                    color: "#eab308",
                                                },
                                                {
                                                    label: "R3 — Alto",
                                                    color: "#f97316",
                                                },
                                                {
                                                    label: "R4 — Muito alto",
                                                    color: "#ef4444",
                                                },
                                            ].map((item) => (
                                                <div key={item.label} className="flex items-center gap-2">
                                                    <span className="h-3 w-3 rounded-[8px]"
                                                        style={{
                                                            backgroundColor: item.color,
                                                        }}
                                                    />
                                                    <span className="text-[11px]">{item.label}</span>
                                                </div>
                                            ))}
                                            {showGeologicalSpecialLegend && (
                                                <>
                                                    <div className="my-1 border-t border-slate-200" />
                                                    {[
                                                        {
                                                            label: "Área encerrada",
                                                            color: "#64748b",
                                                        },
                                                        {
                                                            label: "Em monitoramento",
                                                            color: "#a78bfa",
                                                        },
                                                    ].map((item) => (
                                                        <div key={item.label} className="flex items-center gap-2">
                                                            <span className="h-3 w-3 rounded-[8px]"
                                                                style={{
                                                                    backgroundColor: item.color,
                                                                }}
                                                            />
                                                            <span className="text-[11px]">{item.label}</span>
                                                        </div>
                                                    ))}
                                                </>
                                            )}
                                        </div>
                                    </section>
                                )}
                            </div>
                        )}
                        <div className="pointer-events-none absolute bottom-5 left-5 z-[500] rounded-[8px] border border-[#373a3e] bg-[#1a1b1c]/90 px-3 py-2 shadow-lg backdrop-blur">
                            <p className="text-[11px] text-[#d1d5db]">{activeLayerIds.length === 0 ? "Selecione uma camada para começar" : `${activeLayerIds.length} camada(s) ativa(s)`}</p>
                        </div>
                    </div>
                </section>
            </div>
        </main >
    )
}