export interface ReferenceForImageGeneration {
  type:
    | "image"
    | "gif"
    | "pdf"
    | "video"
    | "youtube"
    | "image-link";

  name: string;
  url: string;

  source?:
    | "input-folder"
    | "external-url"
    | "upload"
    | "google-drive";

  sourceId?: string;
  mimeType?: string;
}


export interface GeneratedImageResponse {
  success: boolean;
  image_url: string;
  filename: string;
  template_id: string;
  model: string;
}


const API_BASE_URL =
  "http://localhost:8000";


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
   * Google Drive
   *
   * The browser preview URL must NOT be
   * sent to the backend.
   *
   * The actual Drive file ID is sent.
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


    return driveFileId;
  }


  /*
   * Local input / manual upload
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
   * External image URL / YouTube
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


export async function generateImage(
  args: {
    reference:
      ReferenceForImageGeneration;

    prompt: string;

    template: unknown;
  },
): Promise<GeneratedImageResponse> {

  const prompt =
    args.prompt.trim();


  if (!prompt) {
    throw new Error(
      "Content prompt is required.",
    );
  }


  const sourceType =
    getSourceType(
      args.reference,
    );


  const source =
    getSource(
      args.reference,
    );


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
    args.reference.name ||
      source,
  );


  formData.append(
    "content_type",
    args.reference.mimeType ||
      "",
  );


  formData.append(
    "prompt",
    prompt,
  );


  formData.append(
    "template_json",
    JSON.stringify(
      args.template,
    ),
  );


  const response =
    await fetch(
      `${API_BASE_URL}/api/images/generate`,
      {
        method: "POST",
        body: formData,
      },
    );


  let data:
    Partial<GeneratedImageResponse> & {
      detail?: string;
    } = {};


  try {

    data =
      await response.json();

  } catch {
    /*
     * Backend may return a
     * non-JSON error.
     */
  }


  if (!response.ok) {

    throw new Error(
      data.detail ||
        "Unable to generate the output image.",
    );
  }


  if (!data.image_url) {

    throw new Error(
      "Image generation completed without an output image.",
    );
  }


  return data as GeneratedImageResponse;
}