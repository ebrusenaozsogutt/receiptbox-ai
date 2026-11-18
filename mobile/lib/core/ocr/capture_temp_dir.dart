import 'dart:io';

/// The one folder where images live for a moment while they are read (resized copies, PDF page
/// images). Everything in it is deleted when processing ends; anything left over (the app was
/// killed mid-way) is deleted at the next start. Nothing here is a place to keep images:
/// storing receipt images is P07.
class CaptureTempDir {
  CaptureTempDir(this._base);

  final Future<Directory> Function() _base;

  Future<Directory> ensure() async {
    final directory = Directory(
      '${(await _base()).path}${Platform.pathSeparator}capture_tmp',
    );
    return directory.create(recursive: true);
  }

  /// Deletes everything that is still in the folder.
  Future<void> clear() async {
    final directory = Directory(
      '${(await _base()).path}${Platform.pathSeparator}capture_tmp',
    );
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  }
}
