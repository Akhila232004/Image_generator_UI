export interface ReferenceForImageGeneration {
  type:
    | "image"
    | "gif"
    | "pdf"
    | "video"
    | "youtube"
    | "image-link";

  name: string;

  /**
   * Browser preview URL.
   *
   * This is used only for displaying the reference
   * in the frontend.
   */
  url: string;

  source?:
    | "input-folder"
    | "external-url"
    | "upload"
    | "google-drive";

  /**
   * Actual backend source.
   *
   * Google Drive -> Drive file ID
   * Upload -> stored filename
   * Input folder -> filename
   * External URL -> HTTP/HTTPS URL
   */
  sourceId?: string;

  mimeType?: string;
}

export interface GeneratedImageResponse {
  success: boolean;

  image_url: string;

  filename: string;

  template_id: string;

  model: string;

  provider?: string;

  api_id?: string;

  pipeline_api_id?: string;
}
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


type BackendSourceType =
  | "input-folder"
  | "google-drive"
  | "upload"
  | "external-url"
  | "youtube";

function getSourceType(
  reference: ReferenceForImageGeneration,
): BackendSourceType {
  if (
    reference.type === "youtube"
  ) {
    return "youtube";
  }

  if (
    reference.source === "google-drive"
  ) {
    return "google-drive";
  }

  if (
    reference.source === "upload"
  ) {
    return "upload";
  }

  if (
    reference.source === "input-folder"
  ) {
    return "input-folder";
  }

  return "external-url";
}

function getSource(
  reference: ReferenceForImageGeneration,
): string {
  const sourceType =
    getSourceType(reference);

  /*
   * ------------------------------------------------------------
   * Google Drive
   * ------------------------------------------------------------
   *
   * Never send the browser preview URL.
   *
   * The backend needs the actual Drive file ID.
   */
  if (
    sourceType === "google-drive"
  ) {
    const driveFileId =
      reference.sourceId?.trim();

    if (!driveFileId) {
      throw new Error(
        "Google Drive reference ID is missing.",
      );
    }

    return driveFileId.replace(
      /^drive:/i,
      "",
    );
  }

  /*
   * ------------------------------------------------------------
   * Local input / manual upload
   * ------------------------------------------------------------
   */
  if (
    sourceType === "upload" ||
    sourceType === "input-folder"
  ) {
    const filename =
      (
        reference.sourceId ||
        reference.name
      ).trim();

    if (!filename) {
      throw new Error(
        "Reference filename is missing.",
      );
    }

    return filename;
  }

  /*
   * ------------------------------------------------------------
   * External image URL / YouTube
   * ------------------------------------------------------------
   */
  const externalSource =
    (
      reference.sourceId ||
      reference.url
    ).trim();

  if (
    !externalSource ||
    !/^https?:\/\//i.test(
      externalSource,
    )
  ) {
    throw new Error(
      "A valid HTTP or HTTPS reference URL is required.",
    );
  }

  return externalSource;
}

/**
 * Generate an image from one or more references.
 *
 * `reference`:
 *   Backward-compatible single-reference API.
 *
 * `references`:
 *   New multi-reference API.
 *
 * When multiple references are supplied, they are sent individually
 * to the backend. The backend is responsible for combining their
 * visual characteristics into one coherent generated image.
 *
 * It must NOT create a collage/contact sheet.
 */
export async function generateImage(
  args: {
    reference?: ReferenceForImageGeneration;

    references?: ReferenceForImageGeneration[];

    prompt: string;

    template: unknown;
  },
): Promise<GeneratedImageResponse> {
  /*
   * ------------------------------------------------------------
   * Validate prompt
   * ------------------------------------------------------------
   */
  const prompt =
    args.prompt.trim();

  if (!prompt) {
    throw new Error(
      "Content prompt is required.",
    );
  }

  /*
   * ------------------------------------------------------------
   * Resolve references
   * ------------------------------------------------------------
   *
   * New multi-reference flow takes priority.
   *
   * If only the old `reference` property is supplied,
   * convert it into a one-item array.
   */
  const references =
    (
      args.references &&
      args.references.length > 0
    )
      ? args.references
      : args.reference
        ? [args.reference]
        : [];

  if (
    references.length === 0
  ) {
    throw new Error(
      "At least one reference image is required.",
    );
  }

  /*
   * ------------------------------------------------------------
   * FormData
   * ------------------------------------------------------------
   */
  const formData =
    new FormData();

  /*
   * Keep the original single-reference
   * fields for backend compatibility.
   */
  const first =
    references[0];

  const firstSourceType =
    getSourceType(first);

  const firstSource =
    getSource(first);

  formData.append(
    "source_type",
    firstSourceType,
  );

  formData.append(
    "source",
    firstSource,
  );

  formData.append(
    "filename",
    first.name ||
      firstSource,
  );

  formData.append(
    "content_type",
    first.mimeType ||
      "",
  );

  /*
   * ------------------------------------------------------------
   * Multiple references
   * ------------------------------------------------------------
   *
   * Every reference remains a separate source.
   *
   * Example:
   *
   * Reference 1 -> person
   * Reference 2 -> clothing
   * Reference 3 -> background
   * Reference 4 -> product
   *
   * The backend receives these separately and
   * synthesizes them into ONE final image.
   */
  const selectedReferences =
    references.map(
      (
        reference,
        index,
      ) => ({
        number:
          index + 1,

        source_type:
          getSourceType(
            reference,
          ),

        source:
          getSource(
            reference,
          ),

        filename:
          reference.name ||
          `reference_${index + 1}.png`,

        content_type:
          reference.mimeType ||
          "",
      }),
    );

  formData.append(
    "references_json",
    JSON.stringify(
      selectedReferences,
    ),
  );

  /*
   * ------------------------------------------------------------
   * User prompt
   * ------------------------------------------------------------
   */
  formData.append(
    "prompt",
    prompt,
  );

  /*
   * ------------------------------------------------------------
   * Generated template
   * ------------------------------------------------------------
   */
  formData.append(
    "template_json",
    JSON.stringify(
      args.template ?? {},
    ),
  );

  /*
   * ------------------------------------------------------------
   * Backend request
   * ------------------------------------------------------------
   */
  const response =
    await fetch(
      `${API_BASE_URL}/api/images/generate`,
      {
        method: "POST",
        body: formData,
        credentials: "include",
      },
    );

  /*
   * ------------------------------------------------------------
   * Parse response
   * ------------------------------------------------------------
   */
  let data:
    Partial<GeneratedImageResponse> & {
      detail?: string;
    } = {};

  try {
    data =
      await response.json();
  } catch {
    /*
     * Backend may return
     * a non-JSON error.
     */
  }

  /*
   * ------------------------------------------------------------
   * Error handling
   * ------------------------------------------------------------
   */
  if (!response.ok) {
    throw new Error(
      data.detail ||
        "Unable to generate the output image.",
    );
  }

  /*
   * ------------------------------------------------------------
   * Validate generated image
   * ------------------------------------------------------------
   */
  if (!data.image_url) {
    throw new Error(
      "Image generation completed without an output image.",
    );
  }

  return data as GeneratedImageResponse;
}