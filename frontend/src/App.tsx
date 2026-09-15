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
import { generatePrompt } from "./services/promptService";

import type {
  GenerateTemplateResponse,
} from "./services/templateService";


const API_BASE_URL = "http://localhost:8000";


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


interface ApiKeyOption {
  id: string;
  name: string;
  keyName: string;
}


interface ApiKeySetupProps {
  onComplete: (
    selectedKeys: string[],
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
       * The backend already groups aliases such as
       * GEMINI_API_KEY and GOOGLE_API_KEY into one
       * logical service.
       *
       * Keep a frontend guard as well so duplicate
       * service names can never appear in the setup UI.
       */

      const seenServices =
        new Set<string>();

      const keys =
        rawKeys.filter(
          (api) => {
            const serviceName =
              api.name
                .trim()
                .toLowerCase();

            if (
              seenServices.has(
                serviceName,
              )
            ) {
              return false;
            }

            seenServices.add(
              serviceName,
            );

            return true;
          },
        );


      if (!keys.length) {
        throw new Error(
          "No supported API keys were found in the uploaded file.",
        );
      }

      setApiKeys(keys);

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


  function toggleApiKey(
    keyId: string,
  ) {
    setSelectedKeys(
      (current) =>
        current.includes(keyId)
          ? current.filter(
              (id) =>
                id !== keyId,
            )
          : [
              ...current,
              keyId,
            ],
    );
  }


  async function handleContinue() {
    if (!selectedKeys.length) {
      setError(
        "Select at least one API before continuing.",
      );

      return;
    }

    setError("");
    setIsSaving(true);

    try {
      const response =
        await fetch(
          `${API_BASE_URL}/api/api-keys/select`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              selected_ids:
                selectedKeys,
            }),
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
              "Unable to activate the selected APIs.",
          ),
        );
      }

      onComplete(
        selectedKeys,
      );

    } catch (err) {
      console.error(
        "API selection failed:",
        err,
      );

      setError(
        err instanceof Error
          ? err.message
          : "Unable to activate the selected APIs.",
      );

    } finally {
      setIsSaving(false);
    }
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

              {apiKeys.length > 0 && (
                <small>
                  {selectedKeys.length} selected
                </small>
              )}

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

                    <label
                      key={api.id}
                      className={`api-key-option ${
                        selectedKeys.includes(
                          api.id,
                        )
                          ? "selected"
                          : ""
                      }`}
                    >

                      <input
                        type="checkbox"
                        checked={selectedKeys.includes(
                          api.id,
                        )}
                        onChange={() =>
                          toggleApiKey(
                            api.id,
                          )
                        }
                      />

                      <span className="api-key-service-icon">
                        {api.name
                          .charAt(0)
                          .toUpperCase()}
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

                      <span className="api-key-state">
                        {selectedKeys.includes(
                          api.id,
                        )
                          ? "Selected"
                          : "Select"}
                      </span>

                    </label>

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
              ? "Activating..."
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
  onBackToApiSetup: () => void;
}


function ImageGenerator({
  selectedApiKeys,
  onBackToApiSetup,
}: ImageGeneratorProps) {

  void selectedApiKeys;


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

  const [templateResult, setTemplateResult] =
    useState<GenerateTemplateResponse | null>(
      null,
    );

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

    if (
      inputFiles.length >
      0
    ) {

      generateInputImageTags(
        inputFiles,
      );

    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputFiles.length]);


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


    try {

      const generatedPrompt =
        await generatePrompt({
          type:
            reference.type,

          name:
            reference.name,

          url:
            reference.url,

          source:
            reference.source as any,

          sourceId:
            reference.sourceId,

          mimeType:
            reference.mimeType,
        });


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

          <div className="active-api-summary">

            <span>
              APIs
            </span>

            <strong>
              {
                selectedApiKeys.length
              }
            </strong>

          </div>


          <button
            type="button"
            className="header-button"
            onClick={onBackToApiSetup}
          >
            ← API Setup
          </button>

          <button
            type="button"
            className="header-button"
          >
            Documentation
          </button>


          <button
            type="button"
            className="settings-button"
            aria-label="Settings"
          >
            ⚙
          </button>

        </div>

      </header>


      <main className="main-content">


        <section className="hero-section">

          <div>

            <h1>
              Transform references into
              reusable visual content.
            </h1>

            <p>
              Select a reference, define the
              template, and prepare it for
              image generation.
            </p>

          </div>

        </section>


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

                  ) : inputFiles.length ===
                    0 ? (

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
                          scrollReferenceList(
                            "up",
                          )
                        }
                        aria-label="Scroll reference images up"
                      >
                        ▲
                      </button>


                      <div
                        ref={
                          referenceListRef
                        }
                        className={`reference-file-list ${
                          isReferenceListAtTop ||
                          isReferenceListAtBottom
                            ? "scrollbar-red"
                            : "scrollbar-green"
                        }`}
                        onScroll={
                          handleReferenceListScroll
                        }
                      >


                        {inputFiles.map(
                          (
                            file,
                          ) => (

                            <label
                              key={
                                file.id
                              }
                              className={`reference-file-item ${
                                selectedInputId ===
                                file.id
                                  ? "selected"
                                  : ""
                              }`}
                            >


                              <input
                                type="checkbox"
                                checked={
                                  selectedInputId ===
                                  file.id
                                }
                                onChange={() =>
                                  handleReferenceSelection(
                                    file,
                                  )
                                }
                                aria-label={`Select ${file.name} as reference`}
                              />


                              <div className="reference-list-thumbnail">

                                <img
                                  src={
                                    previewUrls[
                                      file.id
                                    ] ||
                                    resolveApiUrl(
                                      file.url,
                                    )
                                  }
                                  alt={
                                    file.name
                                  }
                                  loading="eager"
                                  decoding="async"
                                  onError={(
                                    event,
                                  ) => {

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


                                {file.tagError &&
                                  !file.tag && (
                                    <div className="reference-list-file-error">
                                      {
                                        file.tagError
                                      }
                                    </div>
                                  )}


                                <div className="reference-list-file-meta">
                                  {
                                    file.sizeFormatted
                                  }
                                </div>

                              </div>

                            </label>

                          ),
                        )}

                      </div>


                      <button
                        type="button"
                        className={`reference-scroll-button reference-scroll-down ${
                          isReferenceListAtBottom
                            ? "scroll-indicator-bottom"
                            : ""
                        }`}
                        onClick={() =>
                          scrollReferenceList(
                            "down",
                          )
                        }
                        aria-label="Scroll reference images down"
                      >
                        ▼
                      </button>

                    </>

                  )}

                </div>


                <div className="reference-divider">

                  <span>
                    or
                  </span>

                </div>


                <div
                  className="reference-drop-zone"
                  onDragOver={(event) =>
                    event.preventDefault()
                  }
                  onDrop={
                    handleDrop
                  }
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
                    onClick={() =>
                      setShowReferenceModal(
                        true,
                      )
                    }
                  >
                    Add Reference
                  </button>

                </div>

              </>

            ) : (

              <>

                <div className="selected-reference-preview">

                  {
                    renderReferencePreview(
                      reference,
                    )
                  }


                  <div className="reference-type-label">
                    {
                      formatReferenceType(
                        reference.type,
                      )
                    }
                  </div>


                  {reference.tag && (
                    <div className="reference-ai-tag">
                      {
                        reference.tag
                      }
                    </div>
                  )}

                </div>


                <div className="selected-reference-info">

                  <div>

                    <strong>
                      {
                        reference.name
                      }
                    </strong>

                    <span>
                      {
                        reference.source ===
                        "google-drive"
                          ? "From Google Drive"
                          : reference.source ===
                              "input-folder"
                            ? "Manual upload"
                            : "External reference"
                      }
                    </span>

                  </div>


                  <button
                    type="button"
                    className="secondary-button"
                    onClick={
                      handleRemoveReference
                    }
                  >
                    Remove
                  </button>

                </div>


                <button
                  type="button"
                  className="change-reference-button"
                  onClick={() =>
                    setShowReferenceModal(
                      true,
                    )
                  }
                >
                  Change Reference
                </button>

              </>

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
                          templateResult.template.regions.map(
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
                          templateResult.template.style.dominant_colors.map(
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
                      selected reference image
                      and create a reusable
                      template prompt.
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
                    ? "Generated prompt will appear here. You can edit it before sending it to Canva."
                    : "Describe the content you want Canva to generate from the template..."
                }
                rows={6}
              />


              <div className="template-helper">
                Template + Prompt → Canva
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


            <span className="coming-pill">
              Canva + MCP · Coming later
            </span>

          </div>


          <div className="builder-placeholder">

            <div className="placeholder-icon">
              ✦
            </div>


            <div>

              <h3>
                Ready to generate
              </h3>

              <p>
                Template, content prompt and
                AI configuration will be
                connected here.
              </p>

            </div>

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
              output/
            </span>

          </div>


          <div className="output-placeholder">

            <div className="placeholder-icon">
              □
            </div>


            <div>

              <h3>
                No generated outputs yet
              </h3>

              <p>
                Your generated images, PDFs,
                GIFs and videos will appear
                here.
              </p>

            </div>

          </div>

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


function App() {

  const currentPath =
    window.location.pathname.replace(
      /\/+$/,
      "",
    ) || "/";


  const [
    apiSetupComplete,
    setApiSetupComplete,
  ] = useState(false);


  const [
    selectedApiKeys,
    setSelectedApiKeys,
  ] = useState<string[]>([]);


  if (
    currentPath ===
    "/project-manager"
  ) {
    return (
      <ProjectManager />
    );
  }


  if (!apiSetupComplete) {

    return (
      <ApiKeySetup
        onComplete={(
          selectedKeys,
        ) => {

          setSelectedApiKeys(
            selectedKeys,
          );

          setApiSetupComplete(
            true,
          );

        }}
      />
    );
  }


  return (
    <ImageGenerator
      selectedApiKeys={
        selectedApiKeys
      }
      onBackToApiSetup={() => {
        setSelectedApiKeys([]);
        setApiSetupComplete(false);
      }}
    />
  );
}


export default App;