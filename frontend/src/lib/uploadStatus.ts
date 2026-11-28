export const isUploadBusy = (uploadStatus: string | null | undefined) =>
  uploadStatus === "pending" || uploadStatus === "processing";
