package picoc

func LexInit(pc *Picoc) {}
func LexCleanup(pc *Picoc) {}
func LexAnalyse(pc *Picoc, fileName string, source string, sourceLen int, tokenLen *int) any {
	_ = pc
	_ = fileName
	_ = source
	_ = sourceLen
	if tokenLen != nil {
		*tokenLen = 0
	}
	return nil
}
func LexInitParser(parser *ParseState, pc *Picoc, sourceText string, tokenSource any, fileName string, runIt int, setDebugMode int) {
	_ = parser
	_ = pc
	_ = sourceText
	_ = tokenSource
	_ = fileName
	_ = runIt
	_ = setDebugMode
}
func LexGetToken(parser *ParseState, value **Value, incPos int) LexToken { return TokenEOF }
func LexRawPeekToken(parser *ParseState) LexToken { return TokenEOF }
func LexToEndOfMacro(parser *ParseState) {}
func LexCopyTokens(startParser *ParseState, endParser *ParseState) any { return nil }
func LexInteractiveClear(pc *Picoc, parser *ParseState) {}
func LexInteractiveCompleted(pc *Picoc, parser *ParseState) {}
func LexInteractiveStatementPrompt(pc *Picoc) {}
