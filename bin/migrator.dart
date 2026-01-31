import 'dart:convert';
import 'dart:io';

import 'package:args/args.dart';

import 'utils/markdown_converter.dart';

/// Journiv Markdown to Quill Delta Migration Tool
///
/// Converts markdown content to Quill Delta JSON format for database migration.
/// Designed to match the frontend conversion logic exactly for 100% compatibility.
///
/// Exit Codes:
///   0 - Success
///   1 - Invalid arguments
///   2 - Conversion error

Future<void> main(List<String> arguments) async {
  final parser = ArgParser()
    ..addFlag(
      'help',
      abbr: 'h',
      negatable: false,
      help: 'Show usage information',
    )
    ..addFlag(
      'version',
      abbr: 'v',
      negatable: false,
      help: 'Show version information',
    );

  ArgResults args;
  try {
    args = parser.parse(arguments);
  } catch (e) {
    stderr.writeln('Error: Invalid arguments - $e');
    stderr.writeln();
    _printUsage(parser);
    exit(1);
  }

  // Handle flags
  if (args['help'] as bool) {
    _printUsage(parser);
    exit(0);
  }

  if (args['version'] as bool) {
    print('Journiv Markdown Migrator v1.0.0');
    print('Compatible with: markdown_quill 4.3.0, dart_quill_delta 10.8.3');
    exit(0);
  }

  if (args.rest.isNotEmpty) {
    stderr.writeln('Error: Command-line arguments are not supported');
    stderr.writeln('Please provide markdown content via stdin');
    stderr.writeln();
    _printUsage(parser);
    exit(1);
  }

  final markdown = await stdin.transform(utf8.decoder).join();

  // Handle empty content
  if (markdown.isEmpty) {
    // Return minimal valid Delta for empty content
    final emptyDelta = {
      'ops': [
        {'insert': '\n'}
      ]
    };
    print(jsonEncode(emptyDelta));
    exit(0);
  }

  // Reject invalid Unicode code points that can break parsers
  if (RegExp(r'[\uFFFE\uFFFF]').hasMatch(markdown)) {
    stderr.writeln('Error: Input contains invalid Unicode characters (U+FFFE/U+FFFF)');
    exit(2);
  }

  try {
    // Convert markdown to Delta JSON
    final deltaJson = MarkdownConverter.markdownToDeltaJson(markdown);

    // Output JSON to stdout (consumed by Python subprocess)
    print(jsonEncode(deltaJson));
    exit(0);
  } catch (e, stackTrace) {
    stderr.writeln('Error: Failed to convert markdown to Delta');
    stderr.writeln('Exception: $e');
    stderr.writeln('Stack trace: $stackTrace');
    stderr.writeln();
    stderr.writeln('Input markdown (first 500 chars):');
    stderr.writeln(markdown.substring(0, markdown.length > 500 ? 500 : markdown.length));
    exit(2);
  }
}

void _printUsage(ArgParser parser) {
  print('Journiv Markdown to Quill Delta Migration Tool');
  print('');
  print('Usage: echo "<markdown-content>" | migrator [options]');
  print('');
  print('Converts markdown text from stdin to Quill Delta JSON format.');
  print('Output is written to stdout as JSON.');
  print('');
  print('Options:');
  print(parser.usage);
  print('');
  print('Examples:');
  print('  echo "# Heading\\n\\n**Bold** text" | migrator');
  print('  echo "Text with ==highlight==" | migrator');
  print('  cat notes.md | migrator');
  print('');
  print('Exit codes:');
  print('  0 - Success');
  print('  1 - Invalid arguments');
  print('  2 - Conversion error');
}
