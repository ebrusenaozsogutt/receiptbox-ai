import 'dart:io';

/// Deletes a temporary file, ignoring "not there" and "cannot delete" (the capture temp folder
/// is cleared at the next start anyway).
Future<void> deleteQuietly(File? file) async {
  try {
    if (file != null && await file.exists()) await file.delete();
  } on FileSystemException {
    // Nothing more can be done.
  }
}
