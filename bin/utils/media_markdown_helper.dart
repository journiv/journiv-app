/// Helpers for converting between long media URLs and short `![[media:<id>]]`
/// syntax inside markdown. Kept in sync with frontend logic for parity.
class MediaMarkdownHelper {
  MediaMarkdownHelper._();

  /// UUID v4 pattern matching standard format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  /// where x is a hexadecimal digit (case-insensitive).
  static const _mediaIdPattern =
      r'([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})';

  /// Matches media shortcodes: `![[media:uuid]]`
  static final RegExp _shortcodePattern = RegExp(
    '!\\[\\[media:$_mediaIdPattern\\]\\]',
    caseSensitive: false,
  );

  /// Matches markdown image syntax with media URLs: `![alt](http://server/api/v1/media/uuid/signed)`
  /// Handles both regular media URLs and thumbnail URLs (including signed variants).
  static final RegExp _markdownMediaPattern = RegExp(
    '!\\[[^\\]]*\\]\\([^)]*/api/v1/media/$_mediaIdPattern(?:/thumbnail)?(?:/signed)?[^)]*\\)',
    caseSensitive: false,
  );

  /// Matches any markdown image syntax to extract the full URL.
  static final RegExp _markdownImageAnyPattern = RegExp(
    '!\\[[^\\]]*\\]\\(([^)]+)\\)',
    caseSensitive: false,
  );

  /// Matches video placeholders with Journiv media URLs: `:::video <.../api/v1/media/uuid...>:::`
  static final RegExp _videoPlaceholderPattern = RegExp(
    ':::video\\s+\\S*/api/v1/media/$_mediaIdPattern\\S*\\s*:::',
    caseSensitive: false,
  );

  /// Matches any video placeholder to extract the full URL: `:::video <url>:::`
  static final RegExp _videoPlaceholderAnyPattern = RegExp(
    r':::video\s+(\S+?)\s*:::',
    caseSensitive: false,
  );

  /// Matches API path patterns containing media UUIDs (signed or unsigned).
  static final RegExp _apiPathPattern = RegExp(
    '/api/v1/media/$_mediaIdPattern(?:/thumbnail)?(?:/signed)?',
    caseSensitive: false,
  );

  static String? _lookupMappedMediaId(String source, Map<String, String> map) {
    final direct = map[source];
    if (direct != null) return direct;

    final normalizedSource = _normalizeMediaSource(source);
    if (normalizedSource == null) return null;

    for (final entry in map.entries) {
      final normalizedKey = _normalizeMediaSource(entry.key);
      if (normalizedKey != null && normalizedKey == normalizedSource) {
        return entry.value;
      }
    }
    return null;
  }

  static String? _normalizeMediaSource(String source) {
    if (source.startsWith('/')) {
      return source.split('?').first;
    }
    final uri = Uri.tryParse(source);
    if (uri == null) return null;
    if (uri.scheme == 'http' || uri.scheme == 'https') {
      return uri.path;
    }
    return null;
  }

  /// Unescape markdown special characters that were escaped by the DeltaToMarkdown converter.
  ///
  /// Handles: `\-` → `-`, `\{` → `{`, `\}` → `}`, `\:` → `:`
  static String _unescapeMarkdown(String input) {
    return input.replaceAllMapped(RegExp(r'\\([{}\-:])'), (match) => match.group(1)!);
  }

  /// Replace full media URLs (images and videos) with the short `![[media:<id>]]` form.
  ///
  /// The [localSourceToIdMap] parameter maps local file paths (blob URLs, file paths)
  /// to their actual media IDs after upload.
  static String collapseMediaUrls(String markdown, {Map<String, String>? localSourceToIdMap}) {
    final hasAppMediaMatch =
        _markdownMediaPattern.hasMatch(markdown) || _videoPlaceholderPattern.hasMatch(markdown);
    final hasLocalSource = localSourceToIdMap != null && localSourceToIdMap.isNotEmpty;

    if (!hasAppMediaMatch && !hasLocalSource) {
      return markdown;
    }

    var result = _unescapeMarkdown(markdown);

    if (localSourceToIdMap != null && localSourceToIdMap.isNotEmpty) {
      result = result.replaceAllMapped(_videoPlaceholderAnyPattern, (match) {
        final source = match.group(1);
        if (source != null) {
          final id = _lookupMappedMediaId(source, localSourceToIdMap);
          if (id != null) return '![[media:$id]]';
        }
        return match.group(0)!;
      });
    }

    result = result.replaceAllMapped(_videoPlaceholderPattern, (match) {
      final id = match.group(1);
      return id != null ? '![[media:$id]]' : match.group(0)!;
    });

    result = result.replaceAllMapped(_markdownMediaPattern, (match) {
      final id = match.group(1);
      return id != null ? '![[media:$id]]' : match.group(0)!;
    });

    if (localSourceToIdMap != null && localSourceToIdMap.isNotEmpty) {
      result = result.replaceAllMapped(_markdownImageAnyPattern, (match) {
        final source = match.group(1);
        if (source != null) {
          final id = _lookupMappedMediaId(source, localSourceToIdMap);
          if (id != null) return '![[media:$id]]';
        }
        return match.group(0)!;
      });
    }

    if (localSourceToIdMap != null && localSourceToIdMap.isNotEmpty) {
      result = result.replaceAllMapped(_videoPlaceholderAnyPattern, (match) {
        final source = match.group(1);
        if (source != null) {
          final id = _lookupMappedMediaId(source, localSourceToIdMap);
          if (id != null) return '![[media:$id]]';

          if (source.startsWith('blob:') || source.startsWith('file:')) {
            return '> **Video Upload Failed**';
          }
        }
        return match.group(0)!;
      });
    } else {
      result = result.replaceAllMapped(_videoPlaceholderAnyPattern, (match) {
        final source = match.group(1);
        if (source != null && (source.startsWith('blob:') || source.startsWith('file:'))) {
          return '> **Video Upload Failed**';
        }
        return match.group(0)!;
      });
    }

    return result;
  }

  /// Strip media shortcodes when converting to Delta.
  static String stripMediaShortcodes(String markdown) {
    if (!_shortcodePattern.hasMatch(markdown)) return markdown;
    return markdown.replaceAll(_shortcodePattern, '');
  }

  /// Extract a media ID from a URL or shortcode-like string.
  static String? extractMediaIdFromSource(String source) {
    final uri = Uri.tryParse(source);
    final queryMediaId = uri?.queryParameters['media_id'];
    if (queryMediaId != null && queryMediaId.isNotEmpty) {
      return queryMediaId;
    }

    final apiMatch = _apiPathPattern.firstMatch(source);
    if (apiMatch != null) return apiMatch.group(1);

    final idMatch = RegExp(_mediaIdPattern, caseSensitive: false).firstMatch(source);
    return idMatch?.group(1);
  }
}
