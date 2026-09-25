import {
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  ChangeEvent,
  DragEvent,
  UIEvent,
} from "react";

import "./App.css";

import { generateTemplate } from "./services/templateService";
import type {
  GenerateTemplateResponse,
} from "./services/templateService";


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


function resolveApiUrl(url: string): string {
  if (!url) {
    return "";
  }

  if (
    /^https?:\/\//i.test(url) ||
    url.startsWith("blob:")
  ) {
    return url;
  }

  return `${API_BASE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}


type ReferenceType =
  | "image"
  | "gif"
  | "pdf"
  | "video"
  | "youtube"
  | "image-link";


interface InputFile {
  id: string;
  name: string;
  type: string;
  mimeType: string;
  size: number;
  sizeFormatted: string;
  url: string;
  tag?: string;
  tagError?: string;
  source?:
    | "google-drive"
    | "manual-upload"
    | "input-folder";
}


interface ReferenceData {
  type: ReferenceType;
  name: string;
  url: string;
  size?: number;
  mimeType?: string;
  source?:
    | "input-folder"
    | "external-url"
    | "upload"
    | "google-drive";
  /*
   * Backend source is kept separate from the browser preview URL.
   * For Google Drive this is the Drive file ID. For uploaded files it
   * is the backend filename. Never send a browser blob URL to FastAPI.
   */
  sourceId?: string;
  tag?: string;
}


function getReferenceType(
  extension: string,
  mimeType = "",
): ReferenceType {
  const normalizedExtension =
    extension.toLowerCase();

  if (normalizedExtension === ".gif") {
    return "gif";
  }

  if (normalizedExtension === ".pdf") {
    return "pdf";
  }

  if (
    normalizedExtension === ".mp4" ||
    normalizedExtension === ".webm" ||
    normalizedExtension === ".mov"
  ) {
    return "video";
  }

  if (
    normalizedExtension === ".png" ||
    normalizedExtension === ".jpg" ||
    normalizedExtension === ".jpeg" ||
    normalizedExtension === ".webp" ||
    mimeType.startsWith("image/")
  ) {
    return "image";
  }

  return "image";
}


function isYouTubeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);

    return (
      parsed.hostname.includes("youtube.com") ||
      parsed.hostname.includes("youtu.be")
    );
  } catch {
    return false;
  }
}


function isImageUrl(url: string): boolean {
  try {
    const parsed = new URL(url);

    const pathname =
      parsed.pathname.toLowerCase();

    return (
      pathname.endsWith(".png") ||
      pathname.endsWith(".jpg") ||
      pathname.endsWith(".jpeg") ||
      pathname.endsWith(".webp") ||
      pathname.endsWith(".gif")
    );
  } catch {
    return false;
  }
}


function formatReferenceType(
  type: ReferenceType,
): string {
  switch (type) {
    case "image":
      return "Image";

    case "gif":
      return "GIF";

    case "pdf":
      return "PDF";

    case "video":
      return "Video";

    case "youtube":
      return "YouTube";

    case "image-link":
      return "Image Link";

    default:
      return "Reference";
  }
}


// Kept for compatibility with existing reference-type UI helpers.
void formatReferenceType;

interface ApiKeyOption {
  id: string;
  name: string;
  keyName: string;
  displayName?: string;
  duplicateNumber?: number;
}


interface SelectedApiService {
  id: string;
  name: string;
  keyName?: string;
}

interface ApiKeySetupProps {
  onComplete: (
    selectedKeys: string[],
    selectedServices: SelectedApiService[],
  ) => void;
}


function ApiKeySetup({
  onComplete,
}: ApiKeySetupProps) {
  const [apiFile, setApiFile] =
    useState<File | null>(null);

  const [apiKeys, setApiKeys] =
    useState<ApiKeyOption[]>([]);

  const [selectedKeys, setSelectedKeys] =
    useState<string[]>([]);

  const [isUploading, setIsUploading] =
    useState(false);

  const [isSaving, setIsSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const apiFileInputRef =
    useRef<HTMLInputElement | null>(null);


  async function handleApiFile(
    file: File,
  ) {
    setApiFile(file);
    setApiKeys([]);
    setSelectedKeys([]);
    setError("");
    setIsUploading(true);

    try {
      const formData =
        new FormData();

      formData.append(
        "file",
        file,
      );

      const response =
        await fetch(
          `${API_BASE_URL}/api/api-keys/upload`,
          {
            method: "POST",
            body: formData,
          },
        );

      const data =
        await response
          .json()
          .catch(() => null);

      if (!response.ok) {
        throw new Error(
          String(
            data?.detail ||
              "Unable to read the API keys file.",
          ),
        );
      }

      const rawKeys:
        ApiKeyOption[] =
        Array.isArray(data?.keys)
          ? data.keys
          : [];


      /*
       * Keep every supported API entry. If the uploaded file
       * contains the same service more than once, give each
       * duplicate a numbered display name instead of silently
       * removing it.
       */
      const serviceCounts =
        new Map<string, number>();

      const keys = rawKeys.map((api) => {
        const baseName =
          api.name.trim() || "API";
        const normalizedName =
          baseName.toLowerCase();
        const occurrence =
          (serviceCounts.get(normalizedName) || 0) + 1;

        serviceCounts.set(
          normalizedName,
          occurrence,
        );

        return {
          ...api,
          name: baseName,
          displayName: baseName,
          duplicateNumber: occurrence,
        };
      });

      const duplicateTotals =
        new Map<string, number>();

      keys.forEach((api) => {
        const normalizedName =
          api.name.trim().toLowerCase();
        duplicateTotals.set(
          normalizedName,
          (duplicateTotals.get(normalizedName) || 0) + 1,
        );
      });

      const displayKeys = keys.map((api) => {
        const normalizedName =
          api.name.trim().toLowerCase();
        const total =
          duplicateTotals.get(normalizedName) || 1;

        return {
          ...api,
          name:
            total > 1
              ? `${api.displayName} ${api.duplicateNumber}`
              : api.displayName,
        };
      });


      if (!keys.length) {
        throw new Error(
          "No supported API keys were found in the uploaded file.",
        );
      }

      setApiKeys(displayKeys);

    } catch (err) {
      console.error(
        "API key file processing failed:",
        err,
      );

      setError(
        err instanceof Error
          ? err.message
          : "Unable to read the API keys file.",
      );

      setApiFile(null);

    } finally {
      setIsUploading(false);
    }
  }



  function handleDownloadApiTemplate() {
    const templateBlob = new Blob([], {
      type: "application/octet-stream",
    });

    const downloadUrl =
      URL.createObjectURL(templateBlob);

    const link =
      document.createElement("a");

    link.href = downloadUrl;
    link.download = "API Key Template.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(downloadUrl);
  }


  async function handleContinue() {
    if (!apiKeys.length) { setError("Upload an API key file before continuing."); return; }
    setError(""); setIsSaving(true);
    try {
      const services: SelectedApiService[] = apiKeys.map((api) => ({ id: api.id, name: api.name, keyName: api.keyName }));
      onComplete([], services);
    } finally { setIsSaving(false); }
  }

  return (
    <div className="api-setup-shell">

      <div className="api-setup-card">

        <div className="api-setup-header">

          <div className="api-setup-mark">
            ✦
          </div>

          <div>

            <div className="api-setup-kicker">
              INITIAL SETUP
            </div>

            <h1>
              Connect your API keys
            </h1>

            <p>
              Upload your API configuration
              file from your desktop. The file
              is processed by the backend and is
              not saved in the project.
            </p>

          </div>

        </div>


        <div className="api-setup-flow">

          <div className="api-setup-step active">

            <span>
              01
            </span>

            <div>
              <strong>
                Upload API Keys File
              </strong>

              <small>
                Choose the API configuration
                file from your desktop.
              </small>
            </div>

          </div>


          <div className="api-setup-connector" />


          <div
            className={`api-setup-step ${
              apiKeys.length
                ? "active"
                : ""
            }`}
          >

            <span>
              02
            </span>

            <div>

              <strong>
                Select APIs
              </strong>

              <small>
                Choose the services to activate.
              </small>

            </div>

          </div>


          <div className="api-setup-connector" />


          <div
            className={`api-setup-step ${
              selectedKeys.length
                ? "active"
                : ""
            }`}
          >

            <span>
              03
            </span>

            <div>

              <strong>
                Open Workspace
              </strong>

              <small>
                Open the Image Generator.
              </small>

            </div>

          </div>

        </div>


        <div className="api-setup-body">

          <div className="api-upload-panel">

            <input
              ref={apiFileInputRef}
              type="file"
              hidden
              accept=".env,.txt,.json"
              onChange={(event) => {
                const file =
                  event.target.files?.[0];

                if (file) {
                  void handleApiFile(file);
                }

                event.target.value = "";
              }}
            />


            <button
              type="button"
              className="api-upload-button"
              onClick={() =>
                apiFileInputRef.current?.click()
              }
              disabled={isUploading}
            >

              <span className="api-upload-icon">
                ↑
              </span>

              <span>

                <strong>
                  {isUploading
                    ? "Reading API file..."
                    : "Upload API Keys File"}
                </strong>

                <small>
                  .env, .txt or .json
                </small>

              </span>

            </button>


            <button
              type="button"
              className="api-template-download-button"
              onClick={handleDownloadApiTemplate}
              style={{
                width: "100%",
                marginTop: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "10px",
                padding: "12px 16px",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                background: "rgba(255, 255, 255, 0.04)",
                color: "inherit",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <span aria-hidden="true">
                ↓
              </span>

              <span>
                Download API Key Template
              </span>
            </button>


            {apiFile &&
              !isUploading && (
                <div className="api-uploaded-file">

                  <span className="api-file-check">
                    ✓
                  </span>

                  <div>

                    <strong>
                      {apiFile.name}
                    </strong>

                    <small>
                      API configuration loaded
                    </small>

                  </div>

                </div>
              )}

          </div>


          <div className="api-selection-panel">

            <div className="api-selection-heading">

              <div>

                <span>
                  AVAILABLE APIs
                </span>

                <strong>
                  Select API services
                </strong>

              </div>



            </div>


            {isUploading ? (

              <div className="api-setup-empty">

                <div className="api-setup-loader" />

                <strong>
                  Reading API configuration
                </strong>

                <span>
                  Detecting available API services.
                </span>

              </div>

            ) : apiKeys.length === 0 ? (

              <div className="api-setup-empty">

                <div className="api-setup-empty-icon">
                  ◇
                </div>

                <strong>
                  Upload a file to continue
                </strong>

                <span>
                  API values stay hidden. Only API
                  service names will be displayed.
                </span>

              </div>

            ) : (

              <div className="api-key-list">

                {apiKeys.map(
                  (api) => (

                    <div key={api.id} className="api-key-option">


                      <span
                        className="api-key-service-icon"
                        style={{
                          width: "32px",
                          height: "32px",
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          background: "rgba(255,255,255,0.06)",
                          borderRadius: "9px",
                          flexShrink: 0,
                        }}
                      >
                        {getApiServiceIcon(api.name, api.keyName, 24)}
                      </span>

                      <span className="api-key-service-text">

                        <strong>
                          {api.name}
                        </strong>

                        <small>
                          {api.name ===
                          "Google Drive API"
                            ? "OAuth access available"
                            : "API credential detected"}
                        </small>

                      </span>

                    </div>

                  ),
                )}

              </div>

            )}

          </div>

        </div>


        {error && (
          <div className="api-setup-error">
            {error}
          </div>
        )}


        <div className="api-setup-footer">

          <div className="api-security-note">

            <span>
              ✓
            </span>

            <div>

              <strong>
                API values are never displayed
              </strong>

              <small>
                Only API service names appear
                in the selection list.
              </small>

            </div>

          </div>


          <button
            type="button"
            className="api-continue-button"
            disabled={
              !apiKeys.length ||
              !selectedKeys.length ||
              isSaving
            }
            onClick={
              handleContinue
            }
          >

            {isSaving
              ? "Opening Image Generator..."
              : "Continue to Image Generator"}

            <span>
              →
            </span>

          </button>

        </div>

      </div>

    </div>
  );
}


interface ImageGeneratorProps {
  selectedApiKeys: string[];
  selectedApiServices: SelectedApiService[];
  availableApiServices: SelectedApiService[];
  onApiSelectionChange: (keys: string[], services: SelectedApiService[]) => void;
  onBackToApiSetup: () => void;
}


function getApiServiceIcon(
  serviceName: string,
  keyName = "",
  size = 24,
) {
  const normalize = (value: string) =>
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

  const service = normalize(serviceName);
  const key = normalize(keyName);

  /*
   * Provider icon registry
   * ------------------------------------------------------------
   *
   * The key name is checked before the display name. This is
   * important because different environment-variable names can
   * represent the same provider.
   *
   * Provider-specific assets are used instead of rendering the
   * first character of the provider name. Therefore the UI shows
   * only the real provider icon + provider name.
   *
   * Gemini uses Google's official Gemini sparkle asset.
   * Claude uses Claude's product favicon.
   * OpenRouter uses its current official app icon.
   * Other providers use their own official site favicon.
   */
  const brandIcons: Array<{
    matches: string[];
    iconUrl: string;
    alt: string;
  }> = [
    // Google / Gemini
    {
      matches: [
        "gemini api",
        "gemini",
        "google gemini",
        "gemini api key",
        "gemini api key",
        "google api key",
        "google ai api",
        "google ai api key",
        "generative ai api",
      ],
      iconUrl:
        "https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg",
      alt: "Google Gemini",
    },
    {
      matches: [
        "google drive api",
        "google drive",
        "drive api",
        "gdrive api",
      ],
      iconUrl:
        "https://drive.google.com/favicon.ico",
      alt: "Google Drive",
    },
    {
      matches: [
        "google cloud api",
        "google cloud",
        "gcp api",
        "google vertex api",
        "google vertex",
      ],
      iconUrl:
        "https://cloud.google.com/favicon.ico",
      alt: "Google Cloud",
    },
    {
      matches: [
        "google api",
        "google",
      ],
      iconUrl:
        "https://www.google.com/favicon.ico",
      alt: "Google",
    },

    // AI providers — exact product icons
    {
      matches: [
        "openrouter api",
        "openrouter",
        "open router api",
        "open router",
        "openrouter api key",
      ],
      iconUrl:
        "https://openrouter.ai/apple-touch-icon.png",
      alt: "OpenRouter",
    },
    {
      matches: [
        "claude api",
        "claude",
        "claude ai",
        "anthropic claude",
        "anthropic api",
        "anthropic",
        "anthropic api key",
      ],
      iconUrl:
        // "https://claude.ai/favicon.ico",
        "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/claude-ai.svg",
      alt: "Claude",
    },
    {
      matches: [
        "openai api",
        "openai",
        "chatgpt api",
        "chatgpt",
        "openai api key",
      ],
      iconUrl:
        "https://openai.com/favicon.ico",
      alt: "OpenAI",
    },
    {
      matches: [
        "groq api",
        "groq",
        "groq api key",
      ],
      iconUrl:
        "https://groq.com/favicon.ico",
      alt: "Groq",
    },
    {
      matches: [
        "mistral api",
        "mistral",
        "mistralai",
        "mistral ai",
        "mistral ai api",
      ],
      iconUrl:
        "https://mistral.ai/favicon.ico",
      alt: "Mistral AI",
    },
    {
      matches: [
        "cohere api",
        "cohere",
        "cohere api key",
      ],
      iconUrl:
        "https://cohere.com/favicon.ico",
      alt: "Cohere",
    },
    {
      matches: [
        "hugging face api",
        "huggingface api",
        "hugging face",
        "huggingface",
      ],
      iconUrl:
        "https://huggingface.co/favicon.ico",
      alt: "Hugging Face",
    },
    {
      matches: [
        "perplexity api",
        "perplexity",
        "perplexity api key",
      ],
      iconUrl:
        "https://www.perplexity.ai/favicon.ico",
      alt: "Perplexity",
    },
    {
      matches: [
        "deepseek api",
        "deepseek",
        "deepseek api key",
      ],
      iconUrl:
        "https://www.deepseek.com/favicon.ico",
      alt: "DeepSeek",
    },
    {
      matches: [
        "xai api",
        "xai",
        "x ai api",
        "grok api",
        "grok",
        "x ai",
      ],
      iconUrl:
        "https://x.ai/favicon.ico",
      alt: "xAI",
    },
    {
      matches: [
        "qwen api",
        "qwen",
        "alibaba qwen",
      ],
      iconUrl:
        "https://qwen.ai/favicon.ico",
      alt: "Qwen",
    },
    {
      matches: [
        "fireworks api",
        "fireworks",
        "fireworks ai",
      ],
      iconUrl:
        "https://fireworks.ai/favicon.ico",
      alt: "Fireworks AI",
    },
    {
      matches: [
        "together ai api",
        "together api",
        "together ai",
        "together",
      ],
      iconUrl:
        "https://www.together.ai/favicon.ico",
      alt: "Together AI",
    },
    {
      matches: [
        "replicate api",
        "replicate",
      ],
      iconUrl:
        "https://replicate.com/favicon.ico",
      alt: "Replicate",
    },
    {
      matches: [
        "stability ai api",
        "stability ai",
        "stabilityai",
        "stability",
      ],
      iconUrl:
        "https://stability.ai/favicon.ico",
      alt: "Stability AI",
    },
    {
      matches: [
        "elevenlabs api",
        "eleven labs api",
        "elevenlabs",
        "eleven labs",
      ],
      iconUrl:
        "https://elevenlabs.io/favicon.ico",
      alt: "ElevenLabs",
    },
    {
      matches: [
        "assemblyai api",
        "assembly ai api",
        "assemblyai",
        "assembly ai",
      ],
      iconUrl:
        "https://www.assemblyai.com/favicon.ico",
      alt: "AssemblyAI",
    },

    // Microsoft / AWS / Meta
    {
      matches: [
        "azure api",
        "microsoft azure api",
        "azure",
        "microsoft azure",
        "azure openai api",
      ],
      iconUrl:
        "https://azure.microsoft.com/favicon.ico",
      alt: "Microsoft Azure",
    },
    {
      matches: [
        "microsoft api",
        "microsoft",
        "ms graph api",
        "microsoft graph api",
        "graph api",
      ],
      iconUrl:
        "https://www.microsoft.com/favicon.ico",
      alt: "Microsoft",
    },
    {
      matches: [
        "aws api",
        "amazon web services api",
        "amazon web services",
        "amazon api",
        "aws",
      ],
      iconUrl:
        "https://aws.amazon.com/favicon.ico",
      alt: "Amazon Web Services",
    },
    {
      matches: [
        "meta api",
        "meta",
        "facebook api",
        "facebook",
      ],
      iconUrl:
        "https://www.meta.com/favicon.ico",
      alt: "Meta",
    },

    // Developer / data / infrastructure
    {
      matches: ["pinecone api", "pinecone"],
      iconUrl:
        "https://www.pinecone.io/favicon.ico",
      alt: "Pinecone",
    },
    {
      matches: ["github api", "github"],
      iconUrl:
        "https://github.com/favicon.ico",
      alt: "GitHub",
    },
    {
      matches: ["gitlab api", "gitlab"],
      iconUrl:
        "https://gitlab.com/favicon.ico",
      alt: "GitLab",
    },

    // Communication / productivity / design
    {
      matches: ["youtube api", "youtube"],
      iconUrl:
        "https://www.youtube.com/favicon.ico",
      alt: "YouTube",
    },
    {
      matches: ["stripe api", "stripe"],
      iconUrl:
        "https://stripe.com/favicon.ico",
      alt: "Stripe",
    },
    {
      matches: ["twilio api", "twilio"],
      iconUrl:
        "https://www.twilio.com/favicon.ico",
      alt: "Twilio",
    },
    {
      matches: ["sendgrid api", "sendgrid"],
      iconUrl:
        "https://sendgrid.com/favicon.ico",
      alt: "SendGrid",
    },
    {
      matches: ["slack api", "slack"],
      iconUrl:
        "https://slack.com/favicon.ico",
      alt: "Slack",
    },
    {
      matches: ["discord api", "discord"],
      iconUrl:
        "https://discord.com/favicon.ico",
      alt: "Discord",
    },
    {
      matches: ["notion api", "notion"],
      iconUrl:
        "https://www.notion.so/favicon.ico",
      alt: "Notion",
    },
    {
      matches: ["canva api", "canva"],
      iconUrl:
        "https://www.canva.com/favicon.ico",
      alt: "Canva",
    },
    {
      matches: ["figma api", "figma"],
      iconUrl:
        "https://www.figma.com/favicon.ico",
      alt: "Figma",
    },
  ];

  const matchesEntry = (entry: (typeof brandIcons)[number]) =>
    entry.matches.some((match) => {
      const normalizedMatch = normalize(match);

      return (
        key === normalizedMatch ||
        service === normalizedMatch ||
        key.includes(normalizedMatch) ||
        service.includes(normalizedMatch)
      );
    });

  const brand = brandIcons.find(matchesEntry);

  if (brand) {
    return (
      <img
        src={brand.iconUrl}
        alt={`${brand.alt} icon`}
        title={brand.alt}
        aria-hidden="true"
        width={size}
        height={size}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          display: "block",
          objectFit: "contain",
          flexShrink: 0,
          borderRadius: "4px",
        }}
        onError={(event) => {
          /*
           * Never render A, C, O, or any other provider letter.
           * If a remote provider asset is temporarily unavailable,
           * show a neutral icon until the asset loads again.
           */
          const image = event.currentTarget;
          image.style.display = "none";

          const fallback =
            document.createElement("span");

          fallback.innerHTML = `
            <svg
              width="${size}"
              height="${size}"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <circle
                cx="12"
                cy="12"
                r="9"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M8 12h8M12 8v8"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          `;

          fallback.style.width = `${size}px`;
          fallback.style.height = `${size}px`;
          fallback.style.display = "inline-flex";
          fallback.style.alignItems = "center";
          fallback.style.justifyContent = "center";
          fallback.style.color = "#7C6CFF";
          fallback.style.flexShrink = "0";

          image.parentElement?.appendChild(fallback);
        }}
      />
    );
  }

  /*
   * Unknown/custom provider:
   * never use the provider's first letter. Use a neutral API
   * symbol instead so the UI always remains icon + name.
   */
  return (
    <span
      title={`${serviceName} icon`}
      aria-label={`${serviceName} icon`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#7C6CFF",
        flexShrink: 0,
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path
          d="M8 12h8M12 8v8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

function ImageGenerator({
  selectedApiKeys,
  selectedApiServices,
  availableApiServices,
  onApiSelectionChange,
  onBackToApiSetup: _onBackToApiSetup,
}: ImageGeneratorProps) {

  // Retained for compatibility with the API-selection/session flow.
  void selectedApiServices;


  const [inputFiles, setInputFiles] =
    useState<InputFile[]>([]);

  const [selectedInputId, setSelectedInputId] =
    useState("");

  const [reference, setReference] =
    useState<ReferenceData | null>(null);

  const [showReferenceModal, setShowReferenceModal] =
    useState(false);

  const [showUrlInput, setShowUrlInput] =
    useState(false);

  const [externalUrl, setExternalUrl] =
    useState("");

  const [templatePrompt, setTemplatePrompt] =
    useState("");

  const [promptMode, setPromptMode] =
    useState<"manual" | "ai">(
      "manual",
    );

  const [isGeneratingPrompt, setIsGeneratingPrompt] =
    useState(false);

  // Prompt generation state is retained for the existing flow.
  void isGeneratingPrompt;

  const [templateResult, setTemplateResult] =
    useState<GenerateTemplateResponse | null>(
      null,
    );

  const [templateApiProvider, setTemplateApiProvider] =
    useState("");

  const [templateApiModel, setTemplateApiModel] =
    useState("");

  const [promptApiProvider, setPromptApiProvider] =
    useState("");

  const [promptApiModel, setPromptApiModel] =
    useState("");

  const [generatedImageUrl, setGeneratedImageUrl] =
    useState("");

  const [generatedImageFilename, setGeneratedImageFilename] =
    useState("");

  const [generatedImageModel, setGeneratedImageModel] =
    useState("");

  const [generatedImageProvider, setGeneratedImageProvider] =
    useState("");

  const [isSavingGeneratedImage, setIsSavingGeneratedImage] =
    useState(false);

  const [generatedImageSaved, setGeneratedImageSaved] =
    useState(false);

  const [generatedImageSaveMessage, setGeneratedImageSaveMessage] =
    useState("");

  const [generatedTextChanges, setGeneratedTextChanges] =
    useState<Record<string, string>>({});

  const [socialContent, setSocialContent] = useState<{
    linkedin: { text: string; character_count: number; limit: number };
    twitter: { text: string; character_count: number; limit: number };
  } | null>(null);
  const [isGeneratingSocialContent, setIsGeneratingSocialContent] = useState(false);
  const [isSavingSocialContent, setIsSavingSocialContent] = useState(false);
  const [socialContentMessage, setSocialContentMessage] = useState("");
  const [showSocialPreview, setShowSocialPreview] = useState(false);

  const [isGeneratingImage, setIsGeneratingImage] =
    useState(false);

  const [isLoadingInputs, setIsLoadingInputs] =
    useState(false);

  const [isTaggingImages, setIsTaggingImages] =
    useState(false);

  const [isGeneratingTemplate, setIsGeneratingTemplate] =
    useState(false);

  const [previewUrls, setPreviewUrls] =
    useState<Record<string, string>>({});

  const [error, setError] =
    useState("");

  const [urlError, setUrlError] =
    useState("");


  const [
    isReferenceListAtTop,
    setIsReferenceListAtTop,
  ] = useState(true);


  const [
    isReferenceListAtBottom,
    setIsReferenceListAtBottom,
  ] = useState(false);


  const uploadInputRef =
    useRef<HTMLInputElement | null>(
      null,
    );

  const referenceListRef =
    useRef<HTMLDivElement | null>(
      null,
    );


  /*
   * ------------------------------------------------------------
   * Load reference images from Google Drive and manual uploads
   * ------------------------------------------------------------
   */

  async function loadInputFiles() {
    setIsLoadingInputs(true);
    setError("");

    try {
      const response =
        await fetch(
          `${API_BASE_URL}/api/inputs`,
        );

      if (!response.ok) {
        const errorData =
          await response
            .json()
            .catch(() => null);

        throw new Error(
          String(
            errorData?.detail ||
              "Unable to load reference images.",
          ),
        );
      }


      const data =
        await response.json();


      const files: InputFile[] =
        Array.isArray(data)
          ? data
          : Array.isArray(
              data?.files,
            )
            ? data.files
            : [];


      const images =
        files.filter(
          (
            file: InputFile,
          ) =>
            file.type ===
              "image" ||
            file.type ===
              "gif",
        );


      setInputFiles(
        images,
      );


      /*
       * Load the actual image bytes through
       * the backend and create browser blob URLs.
       *
       * This makes Drive previews independent
       * of browser caching and Google Drive's
       * response headers.
       */

      void preloadReferencePreviews(
        images,
      );

    } catch (err) {

      console.error(
        "Loading input files failed:",
        err,
      );


      setError(
        err instanceof Error
          ? err.message
          : "Unable to load reference images.",
      );


      setInputFiles([]);

    } finally {

      setIsLoadingInputs(
        false,
      );
    }
  }


  /*
   * ------------------------------------------------------------
   * FIX:
   * Automatically load Google Drive references
   * when Image Generator opens.
   * ------------------------------------------------------------
   */

  useEffect(() => {
    void loadInputFiles();

    // Load Google Drive references once when
    // the workspace opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  async function preloadReferencePreviews(
    files: InputFile[],
  ) {

    const entries =
      await Promise.all(
        files.map(
          async (
            file,
          ) => {

            try {

              const response =
                await fetch(
                  resolveApiUrl(
                    file.url,
                  ),
                  {
                    cache:
                      "no-store",
                  },
                );


              if (!response.ok) {
                throw new Error(
                  `Preview request failed (${response.status})`,
                );
              }


              const blob =
                await response.blob();


              if (
                !blob.size ||
                !blob.type.startsWith(
                  "image/",
                )
              ) {
                throw new Error(
                  "The backend did not return a valid image.",
                );
              }


              const objectUrl =
                URL.createObjectURL(
                  blob,
                );


              return [
                file.id,
                objectUrl,
              ] as const;

            } catch (
              previewError
            ) {

              console.error(
                "Reference preview failed:",
                file.name,
                previewError,
              );


              return null;
            }
          },
        ),
      );


    setPreviewUrls(
      (current) => {

        const next = {
          ...current,
        };


        entries.forEach(
          (entry) => {

            if (!entry) {
              return;
            }


            const [
              id,
              url,
            ] = entry;


            if (
              current[id] &&
              current[id] !==
                url
            ) {

              URL.revokeObjectURL(
                current[id],
              );
            }


            next[id] =
              url;
          },
        );


        return next;
      },
    );
  }


  useEffect(() => {

  ;

  return () => {

      Object.values(
        previewUrls,
      ).forEach(
        (url) => {

          URL.revokeObjectURL(
            url,
          );

        },
      );

    };

  }, [previewUrls]);


  /*
   * ------------------------------------------------------------
   * Generate AI tags for existing images
   * ------------------------------------------------------------
   */

  async function generateInputImageTags(
    filesToTag: InputFile[] =
      inputFiles,
  ) {

    if (!filesToTag.length) {
      return;
    }


    setIsTaggingImages(true);
    setError("");


    try {

      const response =
        await fetch(
          `${API_BASE_URL}/api/inputs/tag-all`,
          {
            method: "POST",
          },
        );


      const data =
        await response
          .json()
          .catch(() => null);


      if (!response.ok) {

        throw new Error(
          String(
            data?.detail ||
              "Unable to generate image tags.",
          ),
        );
      }


      const tagMapById:
        Record<
          string,
          string
        > = {};


      const tagMapByFilename:
        Record<
          string,
          string
        > = {};


      const errorMapById:
        Record<
          string,
          string
        > = {};


      if (
        Array.isArray(
          data?.results,
        )
      ) {

        data.results.forEach(
          (
            result: {
              id?: string;
              filename?: string;
              tag?: string;
            },
          ) => {

            if (
              result.tag &&
              result.id
            ) {

              tagMapById[
                result.id
              ] =
                result.tag;
            }


            if (
              result.tag &&
              result.filename
            ) {

              tagMapByFilename[
                result.filename
              ] =
                result.tag;
            }

          },
        );

      }


      if (
        Array.isArray(
          data?.errors,
        )
      ) {

        data.errors.forEach(
          (
            result: {
              id?: string;
              filename?: string;
              error?: string;
            },
          ) => {

            const message =
              String(
                result.error ||
                  "Gemini could not generate a tag.",
              );


            if (result.id) {

              errorMapById[
                result.id
              ] =
                message;
            }


            if (
              result.filename
            ) {

              errorMapById[
                `filename:${result.filename}`
              ] =
                message;
            }

          },
        );

      }


      setInputFiles(
        (currentFiles) =>
          currentFiles.map(
            (file) => ({
              ...file,

              tag:
                tagMapById[
                  file.id
                ] ||
                tagMapByFilename[
                  file.name
                ] ||
                file.tag,

              tagError:
                errorMapById[
                  file.id
                ] ||
                errorMapById[
                  `filename:${file.name}`
                ],
            }),
          ),
      );


      setReference(
        (currentReference) => {

          if (!currentReference) {
            return currentReference;
          }


          const updatedTag =
            (
              selectedInputId
                ? tagMapById[
                    selectedInputId
                  ]
                : undefined
            ) ||
            tagMapByFilename[
              currentReference.name
            ];


          if (!updatedTag) {
            return currentReference;
          }


          return {
            ...currentReference,
            tag: updatedTag,
          };
        },
      );


      if (
        Array.isArray(
          data?.errors,
        ) &&
        data.errors.length >
          0
      ) {

        console.error(
          "Gemini tagging errors:",
          data.errors,
        );


        const firstError =
          data.errors[0];


        setError(
          `Image tagging issue: ${String(
            firstError?.error ||
              "Gemini could not tag one or more images.",
          )}`,
        );
      }

    } catch (err) {

      console.error(
        "Image tagging failed:",
        err,
      );


      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate image tags.",
      );

    } finally {

      setIsTaggingImages(
        false,
      );
    }
  }


  /*
   * ------------------------------------------------------------
   * Automatically tag loaded images
   * ------------------------------------------------------------
   */

  useEffect(() => {
    // Do not call the AI tagging endpoint until at least one AI API key
    // has been selected. API selection is the source of truth for the
    // complete AI pipeline.
    if (
      inputFiles.length > 0 &&
      selectedApiKeys.length > 0
    ) {
      void generateInputImageTags(inputFiles);
    }

    // generateInputImageTags is intentionally omitted because it is recreated
    // on render. The effect is driven by the input count and selected-key count.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputFiles.length, selectedApiKeys.length]);


  /*
   * ------------------------------------------------------------
   * Reference selection
   * ------------------------------------------------------------
   */

  function handleReferenceSelection(
    file: InputFile,
  ) {

    setSelectedInputId(
      file.id,
    );

    setTemplatePrompt(
      "",
    );

    setGeneratedImageUrl("");
    setGeneratedImageFilename("");
    setGeneratedImageModel("");

    setPromptMode(
      "manual",
    );

    setError("");


    const extension =
      file.name.includes(".")
        ? `.${file.name
            .split(".")
            .pop()
            ?.toLowerCase()}`
        : "";


    const selectedReference:
      ReferenceData = {

      type:
        getReferenceType(
          extension,
          file.mimeType,
        ),

      name:
        file.name,

      url:
        previewUrls[file.id] ||
        resolveApiUrl(
          file.url,
        ),

      size:
        file.size,

      mimeType:
        file.mimeType,

      source:
        file.source ===
        "google-drive"
          ? "google-drive"
          : file.source ===
              "manual-upload"
            ? "upload"
            : "input-folder",

      /*
       * Keep the real backend source separate from `url`.
       * `url` is allowed to be a blob URL for the browser preview,
       * but template generation needs the Drive file ID/name.
       */
      sourceId:
        file.source === "google-drive"
          ? file.id.replace(/^drive:/, "")
          : file.name,

      tag:
        file.tag,
    };


    setReference(
      selectedReference,
    );


    void generateTemplateForReference(
      selectedReference,
    );
  }


  /*
   * ------------------------------------------------------------
   * Reference list scroll state
   * ------------------------------------------------------------
   */

  function updateReferenceScrollState() {

    const element =
      referenceListRef.current;


    if (!element) {
      return;
    }


    const atTop =
      element.scrollTop <=
      2;


    const atBottom =
      element.scrollTop +
        element.clientHeight >=
      element.scrollHeight -
        2;


    setIsReferenceListAtTop(
      atTop,
    );

    setIsReferenceListAtBottom(
      atBottom,
    );
  }


  function handleReferenceListScroll(
    event: UIEvent<HTMLDivElement>,
  ) {

    const element =
      event.currentTarget;


    const atTop =
      element.scrollTop <=
      2;


    const atBottom =
      element.scrollTop +
        element.clientHeight >=
      element.scrollHeight -
        2;


    setIsReferenceListAtTop(
      atTop,
    );

    setIsReferenceListAtBottom(
      atBottom,
    );
  }


  function scrollReferenceList(
    direction:
      | "up"
      | "down",
  ) {

    if (
      !referenceListRef.current
    ) {
      return;
    }


    referenceListRef.current.scrollBy(
      {
        top:
          direction ===
          "down"
            ? 180
            : -180,

        behavior:
          "smooth",
      },
    );


    window.setTimeout(
      updateReferenceScrollState,
      250,
    );
  }


  /*
   * ------------------------------------------------------------
   * Reference upload
   * ------------------------------------------------------------
   */

  function handleUploadClick() {
    uploadInputRef.current?.click();
  }


  async function handleUploadedFile(
    file: File,
  ) {

    const extension =
      file.name.includes(".")
        ? `.${file.name
            .split(".")
            .pop()
            ?.toLowerCase()}`
        : "";


    const type =
      getReferenceType(
        extension,
        file.type,
      );


    /*
     * Images and GIFs are stored as
     * manual uploads.
     *
     * Google Drive remains the primary
     * reference source.
     */

    if (
      type === "image" ||
      type === "gif"
    ) {

      setError("");
      setIsTaggingImages(
        true,
      );


      try {

        const formData =
          new FormData();


        formData.append(
          "file",
          file,
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/inputs/upload`,
            {
              method:
                "POST",

              body:
                formData,
            },
          );


        const data =
          await response.json();


        if (!response.ok) {

          throw new Error(
            data?.detail ||
              "Unable to upload and tag image.",
          );
        }


        setSelectedInputId(
          data.id,
        );


        setTemplateResult(
          null,
        );


        const uploadedReference:
          ReferenceData = {

          type,

          name:
            data.name,

          url:
            `${API_BASE_URL}${data.url}`,

          size:
            data.size,

          mimeType:
            data.mimeType ||
            data.mime_type ||
            file.type,

          source:
            "upload",

          /*
           * The upload endpoint stores the image in manual_uploads.
           * The backend template endpoint expects the stored filename.
           */
          sourceId:
            data.name,

          tag:
            data.tag,
        };


        setReference(
          uploadedReference,
        );


        void generateTemplateForReference(
          uploadedReference,
        );


        await loadInputFiles();


        setShowReferenceModal(
          false,
        );

        setShowUrlInput(
          false,
        );

      } catch (err) {

        console.error(
          "Image upload and Gemini tagging failed:",
          err,
        );


        setError(
          err instanceof Error
            ? err.message
            : "Unable to upload and tag image.",
        );

      } finally {

        setIsTaggingImages(
          false,
        );
      }


      return;
    }


    /*
     * Keep PDF/video uploads
     * as local references.
     */

    const objectUrl =
      URL.createObjectURL(
        file,
      );


    setSelectedInputId(
      "",
    );

    setTemplateResult(
      null,
    );

    setError("");


    setReference({
      type,

      name:
        file.name,

      url:
        objectUrl,

      size:
        file.size,

      mimeType:
        file.type,

      source:
        "upload",
    });


    setShowReferenceModal(
      false,
    );

    setShowUrlInput(
      false,
    );
  }


  function handleFileInputChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {

    const file =
      event.target.files?.[0];


    if (file) {

      void handleUploadedFile(
        file,
      );
    }


    event.target.value =
      "";
  }


  /*
   * ------------------------------------------------------------
   * Drag and drop
   * ------------------------------------------------------------
   */

  function handleDrop(
    event: DragEvent<HTMLDivElement>,
  ) {

    event.preventDefault();


    const file =
      event.dataTransfer
        .files?.[0];


    if (file) {

      void handleUploadedFile(
        file,
      );
    }
  }


  /*
   * ------------------------------------------------------------
   * External URL
   * ------------------------------------------------------------
   */

  function handleExternalUrl() {

    const url =
      externalUrl.trim();


    if (!url) {

      setUrlError(
        "Please enter a URL.",
      );

      return;
    }


    try {

      new URL(url);

    } catch {

      setUrlError(
        "Please enter a valid URL.",
      );

      return;
    }


    setUrlError("");

    setSelectedInputId(
      "",
    );

    setTemplateResult(
      null,
    );

    setError("");


    let externalReference:
      ReferenceData;


    if (
      isYouTubeUrl(
        url,
      )
    ) {

      externalReference = {

        type:
          "youtube",

        name:
          "YouTube Reference",

        url,

        source:
          "external-url",

        sourceId:
          url,
      };

    } else if (
      isImageUrl(
        url,
      )
    ) {

      externalReference = {

        type:
          "image-link",

        name:
          "External Image",

        url,

        source:
          "external-url",

        sourceId:
          url,
      };

    } else {

      externalReference = {

        type:
          "image-link",

        name:
          "External Reference",

        url,

        source:
          "external-url",

        sourceId:
          url,
      };
    }


    setReference(
      externalReference,
    );


    void generateTemplateForReference(
      externalReference,
    );


    setExternalUrl(
      "",
    );

    setShowUrlInput(
      false,
    );

    setShowReferenceModal(
      false,
    );
  }


  /*
   * ------------------------------------------------------------
   * Remove reference
   * ------------------------------------------------------------
   */

  function handleRemoveReference() {

    if (
      reference?.source ===
        "upload" &&
      reference.url.startsWith(
        "blob:",
      )
    ) {

      URL.revokeObjectURL(
        reference.url,
      );
    }


    setReference(
      null,
    );

    setSelectedInputId(
      "",
    );

    setTemplatePrompt(
      "",
    );

    setPromptMode(
      "manual",
    );

    setTemplateResult(
      null,
    );

    setGeneratedImageUrl("");
    setGeneratedImageFilename("");
    setGeneratedImageModel("");

    setError("");
  }


  /*
   * ------------------------------------------------------------
   * Automatic template generation
   * ------------------------------------------------------------
   */

  async function generateTemplateForReference(
    currentReference: ReferenceData,
  ) {

    if (
      currentReference.type ===
        "pdf" ||
      currentReference.type ===
        "video"
    ) {

      setTemplateResult(
        null,
      );


      setError(
        "Template generation currently supports images, GIFs and YouTube references.",
      );


      return;
    }


    setError("");

    setIsGeneratingTemplate(
      true,
    );

    setTemplateResult(
      null,
    );
    setTemplateApiProvider("");
    setTemplateApiModel("");


    try {

      const result =
        await generateTemplate({
          type:
            currentReference.type,

          name:
            currentReference.name,

          /*
           * `url` is only the browser preview URL.
           * `sourceId` is the value the backend uses to locate the
           * actual reference.
           */
          url:
            currentReference.url,

          source:
            currentReference.source as any,

          sourceId:
            currentReference.sourceId,

          mimeType:
            currentReference.mimeType,
        });


      setTemplateResult(
        result,
      );

      const templateMetadata = result as GenerateTemplateResponse & {
        provider?: string;
        model?: string;
      };
      setTemplateApiProvider(String(templateMetadata.provider || ""));
      setTemplateApiModel(String(templateMetadata.model || ""));

    } catch (err) {

      console.error(
        "Automatic template generation failed:",
        err,
      );


      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate template from the reference.",
      );

    } finally {

      setIsGeneratingTemplate(
        false,
      );
    }
  }


  /*
   * ------------------------------------------------------------
   * Generate AI prompt
   * ------------------------------------------------------------
   */

  async function handleGeneratePrompt() {

    if (!reference) {

      setError(
        "Please select a reference first.",
      );

      return;
    }


    if (
      reference.type ===
        "pdf" ||
      reference.type ===
        "video"
    ) {

      setError(
        "AI prompt generation currently supports images, GIFs, image URLs and YouTube URLs.",
      );

      return;
    }


    setError("");

    setIsGeneratingPrompt(
      true,
    );
    setPromptApiProvider("");
    setPromptApiModel("");


    try {

      const sourceType =
        reference.source === "google-drive"
          ? "google-drive"
          : reference.source === "upload"
            ? "upload"
            : reference.source === "input-folder"
              ? "input-folder"
              : "external-url";

      const source = reference.sourceId || reference.url;
      if (!source || source.startsWith("blob:")) {
        throw new Error("The selected reference is not available to the backend.");
      }

      const formData = new FormData();
      formData.append("source_type", sourceType);
      formData.append("source", source);
      formData.append("filename", reference.name);
      formData.append("content_type", reference.mimeType || "");

      const promptResponse = await fetch(
        `${API_BASE_URL}/api/prompts/generate`,
        { method: "POST", body: formData },
      );
      const promptData = await promptResponse.json().catch(() => null);

      if (!promptResponse.ok) {
        throw new Error(
          String(promptData?.detail || "Unable to generate a prompt with AI."),
        );
      }

      const generatedPrompt = String(promptData?.prompt || "").trim();
      if (!generatedPrompt) {
        throw new Error("The selected API returned an empty prompt.");
      }

      setPromptApiProvider(String(promptData?.provider || ""));
      setPromptApiModel(String(promptData?.model || ""));


      setTemplatePrompt(
        generatedPrompt,
      );


      setPromptMode(
        "ai",
      );

    } catch (err) {

      console.error(
        "AI prompt generation failed:",
        err,
      );


      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate a prompt with AI.",
      );

    } finally {

      setIsGeneratingPrompt(
        false,
      );
    }
  }


  /*
   * ------------------------------------------------------------
   * Generate output image
   * ------------------------------------------------------------
   */

  async function handleGenerateImage() {

    if (!reference) {

      setError(
        "Please select a reference image first.",
      );

      return;
    }


    if (!templateResult) {

      setError(
        "Generate the template before generating the output image.",
      );

      return;
    }


    if (!templatePrompt.trim()) {

      setError(
        "Enter a content prompt before generating the output image.",
      );

      return;
    }


    if (
      reference.type === "pdf" ||
      reference.type === "video" ||
      reference.type === "youtube"
    ) {

      setError(
        "Image generation currently requires an image reference.",
      );

      return;
    }


    setError("");
    setGeneratedImageUrl("");
    setGeneratedImageFilename("");
    setGeneratedImageModel("");
    setGeneratedImageProvider("");
    setGeneratedImageSaved(false);
    setGeneratedImageSaveMessage("");
    setGeneratedTextChanges({});
    setSocialContent(null);
    setSocialContentMessage("");
    setShowSocialPreview(false);
    setIsGeneratingImage(true);


    try {

      const sourceType =
        reference.source ===
        "google-drive"
          ? "google-drive"
          : reference.source ===
              "upload"
            ? "upload"
            : reference.source ===
                "input-folder"
              ? "input-folder"
              : "external-url";


      const source =
        reference.sourceId ||
        reference.url;


      if (
        source.startsWith("blob:")
      ) {

        throw new Error(
          "The selected uploaded reference is not available to the backend.",
        );
      }


      if (!source) {

        throw new Error(
          "Reference source is missing.",
        );
      }


      const formData =
        new FormData();


      formData.append(
        "source_type",
        sourceType,
      );

      formData.append(
        "source",
        source,
      );

      formData.append(
        "filename",
        reference.name,
      );

      formData.append(
        "content_type",
        reference.mimeType || "",
      );

      formData.append(
        "prompt",
        templatePrompt.trim(),
      );

      formData.append(
        "template_json",
        JSON.stringify(
          templateResult.template,
        ),
      );


      const response =
        await fetch(
          `${API_BASE_URL}/api/images/generate`,
          {
            method:
              "POST",
            body:
              formData,
          },
        );


      const data =
        await response
          .json()
          .catch(() => null);


      if (!response.ok) {

        throw new Error(
          String(
            data?.detail ||
              "Unable to generate the output image.",
          ),
        );
      }


      if (!data?.image_url) {

        throw new Error(
          "Image generation completed without an output image.",
        );
      }


      setGeneratedImageUrl(
        resolveApiUrl(
          data.image_url,
        ),
      );

      setGeneratedImageFilename(
        String(
          data.filename ||
            "",
        ),
      );

      setGeneratedImageModel(
        String(
          data.model ||
            "",
        ),
      );
      setGeneratedImageProvider(
        String(
          data.provider ||
            "",
        ),
      );
      setGeneratedImageSaved(false);
      setGeneratedImageSaveMessage("");

      setGeneratedTextChanges(
        data?.changes &&
        typeof data.changes === "object"
          ? data.changes
          : {},
      );

    } catch (err) {

      console.error(
        "Image generation failed:",
        err,
      );


      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate the output image.",
      );

    } finally {

      setIsGeneratingImage(
        false,
      );
    }
  }


  async function handleGenerateSocialContent() {
    if (!generatedImageFilename) return;
    if (!selectedApiKeys.length) { setError("Select at least one API key before generating social content."); return; }
    setError(""); setSocialContentMessage(""); setIsGeneratingSocialContent(true);
    try {
      const formData = new FormData();
      formData.append("filename", generatedImageFilename);
      formData.append("prompt", templatePrompt.trim());
      const response = await fetch(`${API_BASE_URL}/api/social-content/generate`, { method: "POST", body: formData });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(String(data?.detail || "Unable to generate social media descriptions."));
      setSocialContent(data.content); setSocialContentMessage(`Generated using ${String(data.provider || "selected API")}.`);
    } catch (error) { setSocialContent(null); setSocialContentMessage(error instanceof Error ? error.message : "Unable to generate social media descriptions."); }
    finally { setIsGeneratingSocialContent(false); }
  }

  async function handleSaveSocialContent() {
    if (!generatedImageFilename || !socialContent || isSavingSocialContent) return;
    setIsSavingSocialContent(true); setSocialContentMessage("");
    try {
      const formData = new FormData();
      formData.append("filename", generatedImageFilename);
      formData.append("linkedin", socialContent.linkedin.text);
      formData.append("twitter", socialContent.twitter.text);
      const response = await fetch(`${API_BASE_URL}/api/social-content/save-to-drive`, { method: "POST", body: formData });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(String(data?.detail || "Unable to save the social media description."));
      setSocialContentMessage(String(data?.message || "Social media description saved to Google Drive / outputs."));
    } catch (error) { setSocialContentMessage(error instanceof Error ? error.message : "Unable to save the social media description."); }
    finally { setIsSavingSocialContent(false); }
  }

  async function toggleImageGeneratorApiKey(api: SelectedApiService) {
    const nextKeys = selectedApiKeys.includes(api.id) ? selectedApiKeys.filter((id) => id !== api.id) : [...selectedApiKeys, api.id];
    const nextServices = availableApiServices.filter((service) => nextKeys.includes(service.id));
    onApiSelectionChange(nextKeys, nextServices);
    setSocialContent(null); setSocialContentMessage("");
    if (!nextKeys.length) return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/api-keys/select`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_ids: nextKeys }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(String(data?.detail || "Unable to update API selection."));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to update API selection.");
    }
  }

  /*
   * ------------------------------------------------------------
   * Reference preview
   * ------------------------------------------------------------
   */

  function renderReferencePreview(
    currentReference: ReferenceData,
  ) {

    if (
      currentReference.type ===
      "youtube"
    ) {

      return (
        <div className="media-preview youtube-preview">

          <div className="youtube-icon">
            ▶
          </div>

          <div className="youtube-preview-text">

            <strong>
              YouTube Reference
            </strong>

            <span>
              External video reference
            </span>

          </div>

        </div>
      );
    }


    if (
      currentReference.type ===
      "pdf"
    ) {

      return (
        <div className="media-preview document-preview">

          <div className="document-icon">
            PDF
          </div>

          <div className="document-name">
            {currentReference.name}
          </div>

        </div>
      );
    }


    if (
      currentReference.type ===
      "video"
    ) {

      return (
        <video
          src={
            currentReference.url
          }
          controls
          className="reference-media"
        />
      );
    }


    return (
      <img
        src={
          currentReference.url
        }
        alt={
          currentReference.name
        }
        className="reference-media"
        loading="eager"
        decoding="async"
        onError={(event) => {

          console.error(
            "Reference preview failed:",
            currentReference.url,
          );


          event.currentTarget.style.display =
            "none";
        }}
      />
    );
  }


  /*
   * ------------------------------------------------------------
   * UI
   * ------------------------------------------------------------
   */

  const handleSaveGeneratedImageToDrive = async () => {
    if (!generatedImageFilename || isSavingGeneratedImage) return;

    setIsSavingGeneratedImage(true);
    setGeneratedImageSaveMessage("");
    try {
      const formData = new FormData();
      formData.append("filename", generatedImageFilename);

      const response = await fetch(
        `${API_BASE_URL}/api/images/save-to-drive`,
        { method: "POST", body: formData },
      );
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          String(
            data?.detail ||
              "Unable to save the generated image to Google Drive.",
          ),
        );
      }

      setGeneratedImageSaved(true);
      setGeneratedImageSaveMessage(
        String(data?.message || "Saved to Google Drive / outputs."),
      );
    } catch (error) {
      setGeneratedImageSaved(false);
      setGeneratedImageSaveMessage(
        error instanceof Error
          ? error.message
          : "Unable to save the generated image.",
      );
    } finally {
      setIsSavingGeneratedImage(false);
    }
  };

  // These existing handlers are intentionally retained for compatibility
  // with the reference/prompt flow even when the current UI path does not call them.
  void handleRemoveReference;
  void generateTemplateForReference;
  void handleGeneratePrompt;

  return (
    <div className="app-shell">


      <header className="top-header">

        <div className="brand-area">

          <div className="brand-mark">
            ✦
          </div>

          <div>

            <div className="brand-title">
              Image Generator
            </div>

            <div className="brand-subtitle">
              Reference-driven creative
              workspace
            </div>

          </div>

        </div>


        <div className="header-actions">

          <div className="active-api-summary image-generator-api-selector" aria-label="Select API services for the pipeline">
            {availableApiServices.length > 0 ? availableApiServices.map((service) => {
              const selected = selectedApiKeys.includes(service.id);
              return (
                <button key={service.id} type="button" className={`active-api-service ${selected ? "selected" : ""}`} onClick={() => toggleImageGeneratorApiKey(service)} aria-pressed={selected}>
                  <span aria-hidden="true">{getApiServiceIcon(service.name, service.keyName, 18)}</span>
                  <span>{service.name}</span><span className="api-selection-check">{selected ? "✓" : "+"}</span>
                </button>
              );
            }) : <span className="active-api-service">No API keys loaded</span>}
          </div>

        </div>

      </header>

      <main>

        <section className="workflow-section">


          <div className="workflow-step active">

            <span className="workflow-number">
              01
            </span>

            <span className="workflow-label">
              Reference
            </span>

          </div>


          <div className="workflow-line" />


          <div className="workflow-step">

            <span className="workflow-number">
              02
            </span>

            <span className="workflow-label">
              Template
            </span>

          </div>


          <div className="workflow-line" />


          <div className="workflow-step">

            <span className="workflow-number">
              03
            </span>

            <span className="workflow-label">
              Image Builder
            </span>

          </div>


          <div className="workflow-line" />


          <div className="workflow-step">

            <span className="workflow-number">
              04
            </span>

            <span className="workflow-label">
              Output
            </span>

          </div>

        </section>


        <section className="workspace-grid">


          {/* ====================================================
              REFERENCE
              ==================================================== */}

          <article className="workspace-card">


            <div className="card-header">

              <div>

                <div className="section-kicker">
                  REFERENCE
                </div>

                <h2>
                  Reference Image
                </h2>

              </div>


              {reference && (
                <span className="status-pill">
                  Selected
                </span>
              )}

            </div>


            {!reference ? (

              <>

                <div className="reference-file-selector">

                  <div className="selector-header">

                    <div>

                      <strong>
                        Select reference
                      </strong>

                      <span>
                        Choose a reference from
                        Google Drive or upload manually.
                      </span>

                    </div>

                    {isTaggingImages && (
                      <span className="tagging-status">
                        AI tagging...
                      </span>
                    )}

                  </div>

                  {isLoadingInputs ? (

                    <div className="reference-loading">
                      Loading images...
                    </div>

                  ) : inputFiles.length === 0 ? (

                    <div className="reference-empty-list">
                      No Google Drive references
                      found. You can still add a
                      manual upload below.
                    </div>

                  ) : (

                    <>

                      <button
                        type="button"
                        className={`reference-scroll-button reference-scroll-up ${
                          isReferenceListAtTop
                            ? "scroll-indicator-top"
                            : ""
                        }`}
                        onClick={() =>
                          scrollReferenceList("up")
                        }
                        aria-label="Scroll reference images up"
                      >
                        ▲
                      </button>

                      <div
                        ref={referenceListRef}
                        className={`reference-file-list ${
                          isReferenceListAtTop ||
                          isReferenceListAtBottom
                            ? "scrollbar-red"
                            : "scrollbar-green"
                        }`}
                        onScroll={handleReferenceListScroll}
                      >

                        {inputFiles.map((file) => (

                          <label
                            key={file.id}
                            className={`reference-file-item ${
                              selectedInputId === file.id
                                ? "selected"
                                : ""
                            }`}
                          >

                            <input
                              type="checkbox"
                              checked={selectedInputId === file.id}
                              onChange={() =>
                                handleReferenceSelection(file)
                              }
                              aria-label={`Select ${file.name} as reference`}
                            />

                            <div className="reference-list-thumbnail">

                              <img
                                src={
                                  previewUrls[file.id] ||
                                  resolveApiUrl(file.url)
                                }
                                alt={file.name}
                                loading="eager"
                                decoding="async"
                                onError={(event) => {
                                  console.error(
                                    "Reference thumbnail failed:",
                                    file.name,
                                    file.url,
                                  );
                                  event.currentTarget.style.display =
                                    "none";
                                }}
                              />

                            </div>

                            <div className="reference-list-file-info">

                              <div className="reference-list-file-name">
                                {file.name}
                              </div>

                              <div className="reference-list-file-tag">
                                {file.tag ||
                                  (isTaggingImages
                                    ? "Analyzing image..."
                                    : file.tagError
                                      ? "Tagging failed"
                                      : "Tag unavailable")}
                              </div>

                              {file.tagError && !file.tag && (
                                <div className="reference-list-file-error">
                                  {file.tagError}
                                </div>
                              )}

                              <div className="reference-list-file-meta">
                                {file.sizeFormatted}
                              </div>

                            </div>

                          </label>

                        ))}

                      </div>

                      <button
                        type="button"
                        className={`reference-scroll-button reference-scroll-down ${
                          isReferenceListAtBottom
                            ? "scroll-indicator-bottom"
                            : ""
                        }`}
                        onClick={() =>
                          scrollReferenceList("down")
                        }
                        aria-label="Scroll reference images down"
                      >
                        ▼
                      </button>

                    </>

                  )}

                </div>

                <div className="reference-divider">
                  <span>or</span>
                </div>

                <div
                  className="reference-drop-zone"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleDrop}
                >

                  <div className="reference-drop-title">
                    Add another reference
                  </div>

                  <div className="reference-drop-text">
                    Upload media or provide a
                    YouTube or image link.
                  </div>

                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => setShowReferenceModal(true)}
                  >
                    Add Reference
                  </button>

                </div>

              </>

            ) : (

              <div className="reference-selected-layout">

                <div className="reference-selected-list-panel">

                  <div className="reference-file-selector reference-file-selector-compact">

                    <div className="selector-header">

                      <div>

                        <strong>
                          Reference library
                        </strong>

                        <span>
                          Select another image without
                          leaving the current preview.
                        </span>

                      </div>

                      <span className="reference-count-pill">
                        {inputFiles.length} available
                      </span>

                    </div>

                    {isTaggingImages && (
                      <span className="tagging-status compact-tagging-status">
                        AI tagging...
                      </span>
                    )}

                    {isLoadingInputs ? (

                      <div className="reference-loading">
                        Loading images...
                      </div>

                    ) : inputFiles.length === 0 ? (

                      <div className="reference-empty-list">
                        No Google Drive references found.
                      </div>

                    ) : (

                      <>

                        <button
                          type="button"
                          className={`reference-scroll-button reference-scroll-up ${
                            isReferenceListAtTop
                              ? "scroll-indicator-top"
                              : ""
                          }`}
                          onClick={() =>
                            scrollReferenceList("up")
                          }
                          aria-label="Scroll reference images up"
                        >
                          ▲
                        </button>

                        <div
                          ref={referenceListRef}
                          className={`reference-file-list reference-file-list-compact ${
                            isReferenceListAtTop ||
                            isReferenceListAtBottom
                              ? "scrollbar-red"
                              : "scrollbar-green"
                          }`}
                          onScroll={handleReferenceListScroll}
                        >

                          {inputFiles.map((file) => (

                            <label
                              key={file.id}
                              className={`reference-file-item ${
                                selectedInputId === file.id
                                  ? "selected"
                                  : ""
                              }`}
                            >

                              <input
                                type="checkbox"
                                checked={selectedInputId === file.id}
                                onChange={() =>
                                  handleReferenceSelection(file)
                                }
                                aria-label={`Select ${file.name} as reference`}
                              />

                              <div className="reference-list-thumbnail">

                                <img
                                  src={
                                    previewUrls[file.id] ||
                                    resolveApiUrl(file.url)
                                  }
                                  alt={file.name}
                                  loading="eager"
                                  decoding="async"
                                  onError={(event) => {
                                    console.error(
                                      "Reference thumbnail failed:",
                                      file.name,
                                      file.url,
                                    );
                                    event.currentTarget.style.display =
                                      "none";
                                  }}
                                />

                              </div>

                              <div className="reference-list-file-info">

                                <div className="reference-list-file-name">
                                  {file.name}
                                </div>

                                <div className="reference-list-file-tag">
                                  {file.tag ||
                                    (isTaggingImages
                                      ? "Analyzing image..."
                                      : file.tagError
                                        ? "Tagging failed"
                                        : "Tag unavailable")}
                                </div>

                                <div className="reference-list-file-meta">
                                  {file.sizeFormatted}
                                </div>

                              </div>

                            </label>

                          ))}

                        </div>

                        <button
                          type="button"
                          className={`reference-scroll-button reference-scroll-down ${
                            isReferenceListAtBottom
                              ? "scroll-indicator-bottom"
                              : ""
                          }`}
                          onClick={() =>
                            scrollReferenceList("down")
                          }
                          aria-label="Scroll reference images down"
                        >
                          ▼
                        </button>

                      </>

                    )}

                  </div>

                  <button
                    type="button"
                    className="change-reference-button compact-change-reference"
                    onClick={() => setShowReferenceModal(true)}
                  >
                    + Add / Upload Reference
                  </button>

                </div>

                <div className="reference-selected-preview-panel">

                  <div className="selected-reference-preview">

                    {renderReferencePreview(reference)}

                    <div className="reference-type-label">
                      {formatReferenceType(reference.type)}
                    </div>

                    {reference.tag && (
                      <div className="reference-ai-tag">
                        {reference.tag}
                      </div>
                    )}

                  </div>

                  <div className="selected-reference-info">

                    <div>

                      <strong>
                        {reference.name}
                      </strong>

                      <span>
                        {reference.source === "google-drive"
                          ? "From Google Drive"
                          : reference.source === "input-folder"
                            ? "Manual upload"
                            : "External reference"}
                      </span>

                    </div>

                    <button
                      type="button"
                      className="secondary-button"
                      onClick={handleRemoveReference}
                    >
                      Remove
                    </button>

                  </div>

                </div>

              </div>

            )}

            {error && (
              <div className="error-message">
                {error}
              </div>
            )}

          </article>


          {/* ====================================================
              TEMPLATE
              ==================================================== */}

          <article className="workspace-card">


            <div className="card-header">

              <div>

                <div className="section-kicker">
                  TEMPLATE
                </div>

                <h2>
                  Template Builder
                </h2>

              </div>


              {templateResult && (
                <span className="status-pill success">
                  Generated
                </span>
              )}

            </div>


            <div className="template-workspace-grid">


              <div className="template-reference-area">


                <div className="template-panel-heading">

                  <div className="template-panel-index">
                    01
                  </div>


                  <div>

                    <div className="template-preview-label">
                      REFERENCE
                    </div>

                    <h3>
                      Source Visual
                    </h3>

                    <p>
                      The selected reference used to
                      build the template.
                    </p>

                  </div>

                </div>


                <div className="template-reference-frame">


                  {reference ? (

                    <div className="fixed-reference-preview">

                      {
                        renderReferencePreview(
                          reference,
                        )
                      }

                    </div>

                  ) : (

                    <div className="template-no-reference">

                      <div className="template-empty-icon">
                        ✦
                      </div>

                      <strong>
                        Select a reference image
                      </strong>

                      <span>
                        The selected reference will
                        appear here.
                      </span>

                    </div>

                  )}

                </div>


                {reference && (

                  <div className="template-reference-meta">


                    <div className="template-reference-file">

                      <span className="template-file-dot" />


                      <div>

                        <strong>
                          {
                            reference.name
                          }
                        </strong>

                        <span>

                          {
                            reference.source ===
                            "external-url"
                              ? "External reference"
                              : reference.source ===
                                  "upload"
                                ? "Uploaded reference"
                                : reference.source ===
                                    "google-drive"
                                  ? "From Google Drive"
                                  : "Manual upload"
                          }

                        </span>

                      </div>

                    </div>


                    <span className="template-reference-type">

                      {
                        reference.type ===
                        "youtube"
                          ? "YouTube"
                          : reference.type.toUpperCase()
                      }

                    </span>

                  </div>

                )}

              </div>


              <div className="generated-template-panel">


                <div className="generated-template-panel-header">


                  <div className="template-panel-heading">

                    <div className="template-panel-index active">
                      02
                    </div>


                    <div>

                      <div className="template-preview-label">
                        GENERATED TEMPLATE
                      </div>


                      <h3>

                        {
                          isGeneratingTemplate
                            ? "Creating template..."
                            : templateResult
                              ? templateResult.template_name
                              : "Template structure"
                        }

                      </h3>


                      <p>

                        {
                          isGeneratingTemplate
                            ? "Analyzing the reference and extracting its visual structure."
                            : "A reusable structure generated automatically from the reference."
                        }

                      </p>

                    </div>

                  </div>


                  {isGeneratingTemplate && (
                    <span className="template-generating-pill">
                      Generating
                    </span>
                  )}


                  {templateResult &&
                    !isGeneratingTemplate && (
                      <span className="status-pill success">
                        Ready
                      </span>
                    )}

                </div>


                {isGeneratingTemplate ? (

                  <div className="template-generation-state">

                    <div className="template-loader" />

                    <strong>
                      Analyzing reference structure
                    </strong>

                    <span>
                      Reading canvas, layout,
                      regions and visual style
                      from the reference.
                    </span>

                  </div>

                ) : templateResult ? (

                  <div className="generated-template-content">


                    <div className="template-structure-section">


                      <div className="template-structure-heading">

                        <div>

                          <span className="template-section-number">
                            01
                          </span>

                          <strong>
                            Template Overview
                          </strong>

                        </div>

                        <span>
                          Canvas &amp; layout
                        </span>

                      </div>


                      <div className="template-overview-grid">


                        <div className="template-overview-card">

                          <span>
                            Canvas
                          </span>

                          <strong>

                            {
                              templateResult.template.canvas.width
                            }

                            {" × "}

                            {
                              templateResult.template.canvas.height
                            }

                          </strong>

                        </div>


                        <div className="template-overview-card">

                          <span>
                            Orientation
                          </span>

                          <strong>
                            {
                              templateResult.template.canvas.orientation
                            }
                          </strong>

                        </div>


                        <div className="template-overview-card">

                          <span>
                            Layout
                          </span>

                          <strong>
                            {
                              templateResult.template.layout.type
                            }
                          </strong>

                        </div>


                        <div className="template-overview-card">

                          <span>
                            Alignment
                          </span>

                          <strong>
                            {
                              templateResult.template.layout.alignment
                            }
                          </strong>

                        </div>

                      </div>

                    </div>


                    <div className="template-structure-section">


                      <div className="template-structure-heading">

                        <div>

                          <span className="template-section-number">
                            02
                          </span>

                          <strong>
                            Layout Structure
                          </strong>

                        </div>

                        <span>
                          Content regions
                        </span>

                      </div>


                      <div className="template-region-flow">

                        {
                          (Array.isArray(templateResult.template.regions) ? templateResult.template.regions : []).map(
                            (
                              region,
                              index,
                            ) => (

                              <div
                                key={`${region.order}-${region.name}`}
                                className="template-region-node"
                              >

                                <span className="template-region-order">

                                  {
                                    String(
                                      index + 1,
                                    ).padStart(
                                      2,
                                      "0",
                                    )
                                  }

                                </span>


                                <span className="template-region-name">

                                  {
                                    region.name.replaceAll(
                                      "_",
                                      " ",
                                    )
                                  }

                                </span>

                              </div>

                            ),
                          )
                        }

                      </div>

                    </div>


                    <div className="template-structure-section">


                      <div className="template-structure-heading">

                        <div>

                          <span className="template-section-number">
                            03
                          </span>

                          <strong>
                            Visual System
                          </strong>

                        </div>

                        <span>
                          Reference colors
                        </span>

                      </div>


                      <div className="template-color-list structured">

                        {
                          (Array.isArray(templateResult.template.style?.dominant_colors) ? templateResult.template.style.dominant_colors : []).map(
                            (
                              color,
                            ) => (

                              <div
                                key={
                                  color.hex
                                }
                                className="template-color-card"
                              >

                                <span
                                  className="template-color-swatch large"
                                  style={{
                                    backgroundColor:
                                      color.hex,
                                  }}
                                />


                                <div>

                                  <strong>
                                    {
                                      color.hex
                                    }
                                  </strong>

                                  <span>
                                    Reference color
                                  </span>

                                </div>

                              </div>

                            ),
                          )
                        }

                      </div>

                    </div>


                    <div className="template-output-note">


                      <div className="template-output-note-icon">
                        ✓
                      </div>


                      <div>

                        <strong>
                          Ready for Canva
                        </strong>

                        <span>
                          Template structure is generated
                          independently. The human-written
                          or AI-generated prompt can be
                          combined with this template in the
                          next Image Builder step.
                        </span>

                      </div>

                    </div>

                  </div>

                ) : (

                  <div className="template-generation-state empty">

                    <div className="template-empty-icon">
                      ✦
                    </div>

                    <strong>
                      Add a reference to generate a
                      template
                    </strong>

                    <span>
                      The template is created
                      automatically as soon as a
                      reference is selected.
                    </span>

                  </div>

                )}

              </div>

            </div>


            {templateResult && (
              <div className="generated-output-meta" style={{ marginTop: "16px" }}>
                <span>API Provider</span>
                <strong>{templateApiProvider || "Selected API"}</strong>
                <span>Model</span>
                <strong>{templateApiModel || "Provider model"}</strong>
              </div>
            )}


            {templateResult && (
              <div className="template-editable-section">

                <div className="template-structure-heading">
                  <div>
                    <span className="template-section-number">
                      04
                    </span>
                    <strong>
                      Editable Text Groups
                    </strong>
                  </div>

                  <span>
                    Existing text regions that can be replaced
                  </span>
                </div>

                {templateResult?.template?.text_groups &&
                templateResult.template.text_groups.length > 0 ? (
                  <div className="editable-text-list">
                    {(Array.isArray(templateResult?.template?.text_groups) ? templateResult.template.text_groups : []).map((group) => (
                      <div
                        key={group.id}
                        className="editable-text-item"
                      >
                        <div
                          className="editable-text-swatch"
                          style={{
                            backgroundColor:
                              group.lines?.[0]?.color ||
                              "#FFFFFF",
                          }}
                        />
                        <div className="editable-text-copy">
                          <strong>{group.text}</strong>
                          <span>
                            {group.role} · {group.line_count} line{group.line_count === 1 ? "" : "s"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : templateResult?.template?.text_elements &&
                  templateResult.template.text_elements.length > 0 ? (
                  <div className="editable-text-list">
                    {(Array.isArray(templateResult?.template?.text_elements) ? templateResult.template.text_elements : []).map((element) => (
                      <div
                        key={element.id}
                        className="editable-text-item"
                      >
                        <div
                          className="editable-text-swatch"
                          style={{ backgroundColor: element.color }}
                        />
                        <div className="editable-text-copy">
                          <strong>{element.text}</strong>
                          <span>
                            {element.id} · {element.width} × {element.height}px
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="editable-text-empty">
                    No editable text regions were detected. Make sure Gemini is configured and regenerate the template.
                  </div>
                )}

              </div>
            )}


            <div className="template-prompt-area">


              <div className="prompt-mode-header">


                <label className="input-label">
                  Content Prompt
                </label>


                <div className="prompt-mode-options">


                  <label
                    className={`prompt-mode-option ${
                      promptMode ===
                      "manual"
                        ? "active"
                        : ""
                    }`}
                  >

                    <input
                      type="radio"
                      name="prompt-mode"
                      value="manual"
                      checked={
                        promptMode ===
                        "manual"
                      }
                      onChange={() => {

                        setPromptMode(
                          "manual",
                        );

                        setError("");

                      }}
                    />

                    <span>
                      Enter Prompt
                    </span>

                  </label>


                  <label
                    className={`prompt-mode-option ${
                      promptMode ===
                      "ai"
                        ? "active"
                        : ""
                    }`}
                  >

                    <input
                      type="radio"
                      name="prompt-mode"
                      value="ai"
                      checked={
                        promptMode ===
                        "ai"
                      }
                      onChange={() => {

                        setPromptMode(
                          "ai",
                        );

                        setError("");

                      }}
                    />

                    <span>
                      Generate with AI
                    </span>

                  </label>

                </div>

              </div>


              {promptMode ===
                "ai" && (

                <div className="ai-prompt-panel">


                  <div className="ai-prompt-panel-text">

                    <strong>
                      AI Prompt Generator
                    </strong>

                    <span>
                      Gemini will analyze the
                      selected reference and create
                      a content-change prompt that
                      keeps the template design fixed.
                    </span>

                  </div>


                  <button
                    type="button"
                    className="ai-prompt-button"
                    disabled={
                      !reference ||
                      isGeneratingPrompt ||
                      reference.type ===
                        "pdf" ||
                      reference.type ===
                        "video"
                    }
                    onClick={
                      handleGeneratePrompt
                    }
                  >

                    {
                      isGeneratingPrompt
                        ? "Generating Prompt..."
                        : "Generate Prompt with AI"
                    }

                  </button>

                </div>

              )}


              {promptApiProvider && (
                <div className="generated-output-meta" style={{ marginBottom: "12px" }}>
                  <span>API Provider</span>
                  <strong>{promptApiProvider}</strong>
                  <span>Model</span>
                  <strong>{promptApiModel || "Provider model"}</strong>
                </div>
              )}


              <textarea
                id="template-prompt"
                className="template-textarea"
                value={
                  templatePrompt
                }
                onChange={(
                  event,
                ) =>
                  setTemplatePrompt(
                    event.target
                      .value,
                  )
                }
                placeholder={
                  promptMode ===
                  "ai"
                    ? "Generated content-change prompt will appear here. You can edit it before generating the final image."
                    : "Describe which poster text or content should change while keeping the reference design..."
                }
                rows={6}
              />


              <div className="template-helper">
                Reference Design + Content Changes → Final Image
              </div>

            </div>

          </article>

        </section>


        {/* ======================================================
            IMAGE BUILDER
            ====================================================== */}

        <section className="full-width-card">


          <div className="card-header">

            <div>

              <div className="section-kicker">
                IMAGE BUILDER
              </div>

              <h2>
                Generate Image
              </h2>

            </div>


            <span className="status-pill success">
              Reference Design + Content Changes
            </span>

          </div>


          <div className="image-builder-panel">

            <div className="image-builder-summary">

              <div className="image-builder-input-card">
                <span className="image-builder-number">
                  01
                </span>

                <div>
                  <strong>
                    Reference Image
                  </strong>

                  <span>
                    {reference
                      ? reference.name
                      : "Not selected"}
                  </span>
                </div>

              </div>


              <div className="image-builder-plus">
                +
              </div>


              <div className="image-builder-input-card">
                <span className="image-builder-number">
                  02
                </span>

                <div>
                  <strong>
                    Generated Template
                  </strong>

                  <span>
                    {templateResult
                      ? templateResult.template_name
                      : "Not generated"}
                  </span>
                </div>

              </div>


              <div className="image-builder-plus">
                +
              </div>


              <div className="image-builder-input-card">
                <span className="image-builder-number">
                  03
                </span>

                <div>
                  <strong>
                    Content Prompt
                  </strong>

                  <span>
                    {templatePrompt.trim()
                      ? "Prompt ready"
                      : "Enter a prompt below"}
                  </span>
                </div>

              </div>

            </div>


            <button
              type="button"
              className="generate-button"
              disabled={
                !reference ||
                !templateResult ||
                !templatePrompt.trim() ||
                isGeneratingImage
              }
              onClick={
                handleGenerateImage
              }
            >
              {isGeneratingImage
                ? "Generating Image..."
                : "Generate Image"}
            </button>


            {isGeneratingImage && (

              <div className="generation-progress">

                <div className="generation-spinner" />

                <div>
                  <strong>
                    Generating your image
                  </strong>

                  <span>
                    Gemini is identifying the text changes, then the
                    template renderer applies them to the original
                    reference without redrawing the poster.
                  </span>
                </div>

              </div>

            )}

          </div>

        </section>


        {/* ======================================================
            OUTPUT
            ====================================================== */}

        <section className="full-width-card">


          <div className="card-header">

            <div>

              <div className="section-kicker">
                OUTPUT
              </div>

              <h2>
                Generated Output
              </h2>

            </div>


            <span className="output-path">
              Google Drive / outputs
            </span>

          </div>


          {generatedImageUrl ? (

            <div className="generated-output-card">

              <div className="generated-output-preview">

                <img
                  src={
                    generatedImageUrl
                  }
                  alt="Generated output"
                />

              </div>


              <div className="generated-output-details">

                <span className="generated-output-status">
                  Generation complete
                </span>

                <h3>
                  Generated Image
                </h3>

                <p>
                  The original reference remains the visual base.
                  Only the requested editable text/content is replaced
                  using the generated template.
                </p>


                {Object.keys(generatedTextChanges).length > 0 && (
                  <div className="generated-change-list">
                    <span className="generated-change-heading">
                      Applied content changes
                    </span>
                    {Object.entries(generatedTextChanges).map(([id, value]) => (
                      <div key={id} className="generated-change-item">
                        <span>{id}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                )}

                {generatedImageFilename && (

                  <div className="generated-output-meta">

                    <span>
                      File
                    </span>

                    <strong>
                      {generatedImageFilename}
                    </strong>

                  </div>

                )}


                {generatedImageProvider && (
                  <div className="generated-output-meta">
                    <span>API Provider</span>
                    <strong>{generatedImageProvider}</strong>
                  </div>
                )}


                {generatedImageModel && (

                  <div className="generated-output-meta">

                    <span>
                      Model
                    </span>

                    <strong>
                      {generatedImageModel}
                    </strong>

                  </div>

                )}

                <button
                  type="button"
                  className="primary-button"
                  onClick={handleSaveGeneratedImageToDrive}
                  disabled={isSavingGeneratedImage || generatedImageSaved}
                  style={{ marginTop: 16 }}
                >
                  {isSavingGeneratedImage
                    ? "Saving to Google Drive..."
                    : generatedImageSaved
                      ? "Saved to Google Drive / outputs"
                      : "Save to Google Drive"}
                </button>

                {generatedImageSaveMessage && <p style={{ marginTop: 8 }}>{generatedImageSaveMessage}</p>}

                <div className="social-content-panel">
                  <div className="social-content-heading">
                    <div><span className="social-content-kicker">SOCIAL CONTENT</span><h3>Generate Social Media Description</h3><p>Create platform-specific copy from the final generated image.</p></div>
                    <button type="button" className="primary-button social-generate-button" onClick={handleGenerateSocialContent} disabled={isGeneratingSocialContent || !selectedApiKeys.length}>{isGeneratingSocialContent ? "Generating Description..." : "Generate Description"}</button>
                  </div>
                  {socialContent && <div className="social-content-actions"><button type="button" className="secondary-button" onClick={() => setShowSocialPreview((value) => !value)}>{showSocialPreview ? "Hide Preview" : "Preview Description"}</button><button type="button" className="primary-button" onClick={handleSaveSocialContent} disabled={isSavingSocialContent}>{isSavingSocialContent ? "Saving Description..." : "Save Description"}</button></div>}
                  {showSocialPreview && socialContent && (
                    <div className="social-preview-grid">
                      <article className="social-preview-card"><div className="social-preview-card-header"><strong>LinkedIn</strong><span>{socialContent.linkedin.character_count}/{socialContent.linkedin.limit}</span></div><p>{socialContent.linkedin.text}</p></article>
                      <article className="social-preview-card"><div className="social-preview-card-header"><strong>X / Twitter</strong><span>{socialContent.twitter.character_count}/{socialContent.twitter.limit}</span></div><p>{socialContent.twitter.text}</p></article>
                    </div>
                  )}
                  {socialContentMessage && <p className="social-content-message">{socialContentMessage}</p>}
                </div>

              </div>

            </div>

          ) : (

            <div className="output-placeholder">

              <div className="placeholder-icon">
                □
              </div>


              <div>

                <h3>
                  No generated outputs yet
                </h3>

                <p>
                  Enter a content prompt and
                  generate an image using the
                  selected reference and template.
                </p>

              </div>

            </div>

          )}

        </section>

      </main>


      {/* ========================================================
          REFERENCE MODAL
          ======================================================== */}

      {showReferenceModal && (

        <div
          className="modal-backdrop"
          onMouseDown={() =>
            setShowReferenceModal(
              false,
            )
          }
        >

          <div
            className="reference-modal"
            onMouseDown={(
              event,
            ) =>
              event.stopPropagation()
            }
          >


            <div className="modal-header">

              <div>

                <div className="section-kicker">
                  REFERENCE
                </div>

                <h2>
                  Add Reference
                </h2>

              </div>


              <button
                type="button"
                className="modal-close"
                onClick={() =>
                  setShowReferenceModal(
                    false,
                  )
                }
              >
                ×
              </button>

            </div>


            <div className="modal-options">


              <button
                type="button"
                className="modal-option"
                onClick={
                  handleUploadClick
                }
              >

                <span className="modal-option-icon">
                  ↑
                </span>


                <span>

                  <strong>
                    Upload Media
                  </strong>

                  <small>
                    PNG, JPG, WEBP, GIF,
                    PDF, MP4 and more
                  </small>

                </span>

              </button>


              <button
                type="button"
                className="modal-option"
                onClick={() =>
                  setShowUrlInput(
                    !showUrlInput,
                  )
                }
              >

                <span className="modal-option-icon">
                  ↗
                </span>


                <span>

                  <strong>
                    Use Link
                  </strong>

                  <small>
                    YouTube or image URL
                  </small>

                </span>

              </button>

            </div>


            {showUrlInput && (

              <div className="url-input-area">


                <input
                  type="url"
                  value={
                    externalUrl
                  }
                  onChange={(
                    event,
                  ) => {

                    setExternalUrl(
                      event.target
                        .value,
                    );

                    setUrlError("");

                  }}
                  placeholder="https://..."
                  className="url-input"
                />


                <button
                  type="button"
                  className="primary-button"
                  onClick={
                    handleExternalUrl
                  }
                >
                  Add Link
                </button>


                {urlError && (
                  <div className="error-message">
                    {urlError}
                  </div>
                )}

              </div>

            )}


            <input
              ref={
                uploadInputRef
              }
              type="file"
              hidden
              accept="
                image/png,
                image/jpeg,
                image/webp,
                image/gif,
                application/pdf,
                video/mp4,
                video/webm,
                video/quicktime
              "
              onChange={
                handleFileInputChange
              }
            />

          </div>

        </div>

      )}

    </div>
  );
}


function ProjectManager() {
  return null;
}


/*
 * ------------------------------------------------------------
 * Application session persistence
 * ------------------------------------------------------------
 *
 * Keep navigation state for the current browser session.
 * Only non-secret state is stored here:
 *   - whether API setup has been completed
 *   - selected API service IDs
 *   - selected API service names (for display only)
 *
 * Actual API credentials are never stored in browser
 * sessionStorage.
 */
const APP_SESSION_KEY =
  "image-generator-ui-session";


interface AppSessionState {
  apiSetupComplete: boolean;
  selectedApiKeys: string[];
  selectedApiServices: SelectedApiService[];
}


function readAppSession(): AppSessionState {
  const defaultSession: AppSessionState = {
    apiSetupComplete: false,
    selectedApiKeys: [],
    selectedApiServices: [],
  };

  try {
    const stored =
      window.sessionStorage.getItem(
        APP_SESSION_KEY,
      );

    if (!stored) {
      return defaultSession;
    }

    const parsed =
      JSON.parse(stored) as Partial<AppSessionState>;

    return {
      apiSetupComplete:
        parsed.apiSetupComplete === true,
      selectedApiKeys:
        Array.isArray(parsed.selectedApiKeys)
          ? parsed.selectedApiKeys.filter(
              (value): value is string =>
                typeof value === "string",
            )
          : [],
      selectedApiServices:
        Array.isArray(parsed.selectedApiServices)
          ? parsed.selectedApiServices
              .filter(
                (service): service is SelectedApiService =>
                  Boolean(service) &&
                  typeof service === "object" &&
                  typeof (service as SelectedApiService).id === "string" &&
                  typeof (service as SelectedApiService).name === "string",
              )
              .map((service) => ({
                id: service.id,
                name: service.name,
              }))
          : [],
    };
  } catch (error) {
    console.warn(
      "Unable to restore application session:",
      error,
    );

    return defaultSession;
  }
}


function writeAppSession(
  state: AppSessionState,
) {
  try {
    window.sessionStorage.setItem(
      APP_SESSION_KEY,
      JSON.stringify({
        apiSetupComplete:
          state.apiSetupComplete,
        selectedApiKeys:
          state.selectedApiKeys,
        selectedApiServices:
          state.selectedApiServices,
      }),
    );
  } catch (error) {
    console.warn(
      "Unable to save application session:",
      error,
    );
  }
}


function App() {

  const currentPath =
    window.location.pathname.replace(
      /\/+$/,
      "",
    ) || "/";


  /*
   * Restore the last application stage and
   * selected API service IDs when the page is
   * refreshed during the same browser session.
   */
  const [
    initialAppSession,
  ] = useState<AppSessionState>(
    () => readAppSession(),
  );


  const [
    apiSetupComplete,
    setApiSetupComplete,
  ] = useState(
    initialAppSession.apiSetupComplete,
  );


  const [
    selectedApiKeys,
    setSelectedApiKeys,
  ] = useState<string[]>(
    initialAppSession.selectedApiKeys,
  );


  const [
    selectedApiServices,
    setSelectedApiServices,
  ] = useState<SelectedApiService[]>(
    initialAppSession.selectedApiServices,
  );

  const [availableApiServices, setAvailableApiServices] = useState<SelectedApiService[]>(initialAppSession.selectedApiServices);


  /*
   * Keep BOTH screens mounted.
   *
   * This is important: when the user goes from
   * Image Generator back to API Setup, the
   * ImageGenerator component is hidden rather
   * than destroyed. Therefore all of its current
   * reference, template, prompt, output and UI
   * state remains exactly where the user left it.
   */
  const showApiSetup =
    !apiSetupComplete;

  const showImageGenerator =
    apiSetupComplete;


  /*
   * Keep the browser-session state synchronized.
   * This stores only service IDs and navigation
   * state, never the actual API credentials.
   */
  useEffect(() => {
    writeAppSession({
      apiSetupComplete,
      selectedApiKeys,
      selectedApiServices,
    });
  }, [
    apiSetupComplete,
    selectedApiKeys,
    selectedApiServices,
  ]);


  if (
    currentPath ===
      "/project-manager" ||
    currentPath ===
      "/projectmanager"
  ) {
    return (
      <ProjectManager />
    );
  }


;

  return (
    <>
      <div
        style={{
          display:
            showApiSetup
              ? "block"
              : "none",
        }}
        aria-hidden={
          !showApiSetup
        }
      >
        <ApiKeySetup
          onComplete={(
            selectedKeys,
            selectedServices,
          ) => {
            void selectedKeys;

            /*
             * Do NOT clear anything when moving
             * between API Setup and Image Generator.
             */
            setSelectedApiKeys(
              selectedKeys,
            );

            setSelectedApiServices(
              selectedServices,
            );

            setAvailableApiServices(selectedServices);

            setApiSetupComplete(
              true,
            );

          }}
        />
      </div>


      <div
        style={{
          display:
            showImageGenerator
              ? "block"
              : "none",
        }}
        aria-hidden={
          !showImageGenerator
        }
      >
        <ImageGenerator
          selectedApiKeys={
            selectedApiKeys
          }
          selectedApiServices={
            selectedApiServices
          }
          availableApiServices={availableApiServices}
          onApiSelectionChange={(keys, services) => {
            setSelectedApiKeys(keys);
            setSelectedApiServices(services);
          }}
          onBackToApiSetup={() => {

            /*
             * IMPORTANT:
             * Do not clear selectedApiKeys.
             * Do not destroy ImageGenerator.
             *
             * Only switch the visible stage.
             */
            setApiSetupComplete(
              false,
            );

          }}
        />
      </div>
    </>
  );
}


export default App;