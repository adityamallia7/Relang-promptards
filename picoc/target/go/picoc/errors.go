package picoc

import (
	"fmt"
	"io"
	"os"
	"strings"
)

func printSourceTextErrorLine(stream io.Writer, fileName string, sourceText string, line int, characterPos int) {
	if stream == nil {
		stream = os.Stdout
	}
	if sourceText != "" {
		lineCount := 1
		linePos := 0
		for linePos < len(sourceText) && lineCount < line {
			if sourceText[linePos] == '\n' {
				lineCount++
			}
			linePos++
		}
		end := linePos
		for end < len(sourceText) && sourceText[end] != '\n' {
			end++
		}
		fmt.Fprint(stream, sourceText[linePos:end])
		fmt.Fprint(stream, "\n")
		for i := 0; i < characterPos; i++ {
			fmt.Fprint(stream, " ")
		}
	} else {
		for i := 0; i < characterPos+len("picoc> "); i++ {
			fmt.Fprint(stream, " ")
		}
	}
	fmt.Fprintf(stream, "^\n%s:%d:%d ", fileName, line, characterPos)
}

func ProgramFail(parser *ParseState, message string, args ...any) {
	if parser != nil && parser.pc != nil {
		printSourceTextErrorLine(parser.pc.CStdOut, parser.FileName, parser.SourceText, parser.Line, parser.CharacterPos)
		PlatformVPrintf(parser.pc.CStdOut, message, args)
		PlatformPrintf(parser.pc.CStdOut, "\n")
		PlatformExit(parser.pc, 1)
		return
	}
	panic(fmt.Sprintf(message, args...))
}

func ProgramFailNoParser(pc *Picoc, message string, args ...any) {
	if pc != nil && pc.CStdOut != nil {
		PlatformVPrintf(pc.CStdOut, message, args)
		PlatformPrintf(pc.CStdOut, "\n")
		PlatformExit(pc, 1)
		return
	}
	panic(fmt.Sprintf(message, args...))
}

func AssignFail(parser *ParseState, format string, type1 *ValueType, type2 *ValueType, num1 int, num2 int, funcName string, paramNo int) {
	stream := parser.pc.CStdOut
	printSourceTextErrorLine(stream, parser.FileName, parser.SourceText, parser.Line, parser.CharacterPos)
	if funcName == "" {
		PlatformPrintf(stream, "can't assign ")
	} else {
		PlatformPrintf(stream, "can't set ")
	}
	if type1 != nil {
		PlatformPrintf(stream, format, type1, type2)
	} else {
		PlatformPrintf(stream, format, num1, num2)
	}
	if funcName != "" {
		PlatformPrintf(stream, " in argument %d of call to %s()", paramNo, funcName)
	}
	PlatformPrintf(stream, "\n")
	PlatformExit(parser.pc, 1)
}

func LexFail(pc *Picoc, lexer *LexState, message string, args ...any) {
	printSourceTextErrorLine(pc.CStdOut, lexer.FileName, lexer.SourceText, lexer.Line, lexer.CharacterPos)
	PlatformVPrintf(pc.CStdOut, message, args)
	PlatformPrintf(pc.CStdOut, "\n")
	PlatformExit(pc, 1)
}

func PlatformPrintf(stream io.Writer, format string, args ...any) {
	PlatformVPrintf(stream, format, args)
}

func PlatformVPrintf(stream io.Writer, format string, args ...any) {
	if stream == nil {
		stream = os.Stdout
	}
	if len(args) == 0 {
		fmt.Fprint(stream, format)
		return
	}
	replaced := strings.ReplaceAll(format, "%t", "%v")
	fmt.Fprintf(stream, replaced, args...)
}

func PlatformMakeTempName(pc *Picoc, tempNameBuffer string) string {
	_ = pc
	return tempNameBuffer
}
