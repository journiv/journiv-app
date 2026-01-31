import 'dart:io';

import 'package:markdown/markdown.dart' as md;

import 'media_markdown_helper.dart';

const _highlightPattern = r'==(.+?)==';
const _underlinePattern = r'<u>(.+?)</u>';
const _videoPattern = r':::video\s+(\S+?)\s*:::';
const _audioPattern = r':::audio\s+(\S+?)\s*:::';

/// Simplified Markdown to Delta converter for migration binary.
///
/// Converts markdown AST to Quill Delta JSON format without Flutter dependencies.
class MarkdownConverter {
  MarkdownConverter._();

  /// Converts Markdown string to Quill Delta JSON.
  ///
  /// Returns a Map representing the Delta JSON structure:
  /// ```json
  /// {
  ///   "ops": [
  ///     {"insert": "Bold", "attributes": {"bold": true}},
  ///     {"insert": " text\n"}
  ///   ]
  /// }
  /// ```
  static Map<String, dynamic> markdownToDeltaJson(String markdown) {
    final trimmedMarkdown = MediaMarkdownHelper.stripMediaShortcodes(markdown.trimRight());

    if (trimmedMarkdown.isEmpty) {
      return {
        'ops': [
          {'insert': '\n'}
        ]
      };
    }

    try {
      final markdownDocument = md.Document(
        encodeHtml: false,
        extensionSet: md.ExtensionSet.gitHubFlavored,
        inlineSyntaxes: [
          _HighlightSyntax(),
          _UnderlineSyntax(),
          _VideoSyntax(),
          _AudioSyntax(),
        ],
      );

      final ast = markdownDocument.parseLines(trimmedMarkdown.split('\n'));
      final ops = _convertNodesToOps(ast);

      if (ops.isEmpty ||
          !(ops.last['insert'] is String && (ops.last['insert'] as String).endsWith('\n'))) {
        ops.add({'insert': '\n'});
      }

      return {'ops': ops};
    } catch (e, stackTrace) {
      stderr.writeln('Warning: Failed to convert markdown to delta: $e');
      stderr.writeln('Stack trace: $stackTrace');
      stderr.writeln('Returning raw text fallback');
      return {
        'ops': [
          {'insert': trimmedMarkdown},
          {'insert': '\n'}
        ]
      };
    }
  }

  static List<Map<String, dynamic>> _convertNodesToOps(List<md.Node> nodes) {
    final ops = <Map<String, dynamic>>[];

    for (final node in nodes) {
      _processNode(node, ops, {});
    }

    return ops;
  }

  static void _processNode(
    md.Node node,
    List<Map<String, dynamic>> ops,
    Map<String, dynamic> currentAttributes, {
    String? listType,
  }) {
    if (node is md.Element) {
      final newAttributes = Map<String, dynamic>.from(currentAttributes);
      String? currentListType = listType;

      switch (node.tag) {
        case 'h1':
          newAttributes['header'] = 1;
          break;
        case 'h2':
          newAttributes['header'] = 2;
          break;
        case 'h3':
          newAttributes['header'] = 3;
          break;
        case 'h4':
          newAttributes['header'] = 4;
          break;
        case 'h5':
          newAttributes['header'] = 5;
          break;
        case 'h6':
          newAttributes['header'] = 6;
          break;
        case 'blockquote':
          newAttributes['blockquote'] = true;
          break;
        case 'code':
          if (node.attributes['class']?.startsWith('language-') ?? false) {
            newAttributes['code-block'] = true;
          } else {
            newAttributes['code'] = true;
          }
          break;
        case 'pre':
          newAttributes['code-block'] = true;
          break;
        case 'ul':
          currentListType = 'bullet';
          break;
        case 'ol':
          currentListType = 'ordered';
          break;
        case 'li':
          if (listType != null) {
            newAttributes['list'] = listType;
          }
          if ((node.children?.isNotEmpty ?? false) && node.children!.first is md.Element) {
            final firstChild = node.children!.first as md.Element;
            if (firstChild.tag == 'input' && firstChild.attributes['type'] == 'checkbox') {
              if (firstChild.attributes.containsKey('checked')) {
                newAttributes['list'] = 'checked';
              } else {
                newAttributes['list'] = 'unchecked';
              }
              node.children!.removeAt(0);
            }
          }
          break;
        case 'strong':
        case 'b':
          newAttributes['bold'] = true;
          break;
        case 'em':
        case 'i':
          newAttributes['italic'] = true;
          break;
        case 'u':
        case 'ins':
          newAttributes['underline'] = true;
          break;
        case 'mark':
          newAttributes['highlight'] = true;
          break;
        case 's':
        case 'del':
          newAttributes['strike'] = true;
          break;
        case 'a':
          newAttributes['link'] = node.attributes['href'];
          break;
        case 'img':
          final src = node.attributes['src'];
          if (src != null) {
            ops.add({
              'insert': {
                'image': src,
              },
            });
            return;
          }
          break;
        case 'video':
          final src = node.attributes['src'];
          if (src != null) {
            ops.add({
              'insert': {
                'video': src,
              },
            });
            return;
          }
          break;
        case 'audio':
          final src = node.attributes['src'];
          if (src != null) {
            ops.add({
              'insert': {
                'audio': src,
              },
            });
            return;
          }
          break;
        case 'br':
          ops.add(
              {'insert': '\n', if (currentAttributes.isNotEmpty) 'attributes': currentAttributes});
          return;
        case 'p':
          for (final child in node.children ?? <md.Node>[]) {
            _processNode(child, ops, newAttributes, listType: currentListType);
          }
          ops.add({'insert': '\n', if (newAttributes.isNotEmpty) 'attributes': newAttributes});
          return;
      }

      for (final child in node.children ?? <md.Node>[]) {
        _processNode(child, ops, newAttributes, listType: currentListType);
      }

      if (_isBlockElement(node.tag)) {
        ops.add({'insert': '\n', if (newAttributes.isNotEmpty) 'attributes': newAttributes});
      }
    } else if (node is md.Text) {
      final text = node.text;
      if (text.isNotEmpty) {
        ops.add({
          'insert': text,
          if (currentAttributes.isNotEmpty) 'attributes': currentAttributes,
        });
      }
    }
  }

  static bool _isBlockElement(String tag) {
    return const ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'ul', 'ol', 'li']
        .contains(tag);
  }
}

/// Custom markdown syntax for ==highlight== text
class _HighlightSyntax extends md.InlineSyntax {
  _HighlightSyntax() : super(_highlightPattern, startCharacter: 0x3d /* '=' */);

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final text = match[1];
    if (text == null || text.isEmpty) {
      return false;
    }
    parser.addNode(md.Element.text('mark', text));
    return true;
  }
}

/// Custom markdown syntax for <u>underline</u> text
class _UnderlineSyntax extends md.InlineSyntax {
  _UnderlineSyntax() : super(_underlinePattern, startCharacter: 0x3c /* '<' */);

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final text = match[1];
    if (text == null || text.isEmpty) {
      return false;
    }
    parser.addNode(md.Element.text('u', text));
    return true;
  }
}

/// Custom markdown syntax for :::video url::: placeholders
class _VideoSyntax extends md.InlineSyntax {
  _VideoSyntax() : super(_videoPattern, startCharacter: 0x3a /* ':' */);

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final url = match[1];
    if (url == null || url.isEmpty) {
      return false;
    }
    final element = md.Element('video', []);
    element.attributes['src'] = url;
    parser.addNode(element);
    return true;
  }
}

/// Custom markdown syntax for :::audio url::: placeholders
class _AudioSyntax extends md.InlineSyntax {
  _AudioSyntax() : super(_audioPattern, startCharacter: 0x3a /* ':' */);

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final url = match[1];
    if (url == null || url.isEmpty) {
      return false;
    }
    final element = md.Element('audio', []);
    element.attributes['src'] = url;
    parser.addNode(element);
    return true;
  }
}
