package picoc

func PicocParse(pc *Picoc, fileName string, source string, sourceLen int, runIt bool, cleanupNow bool, cleanupSource bool, enableDebugger bool) {
	_ = pc
	_ = fileName
	_ = source
	_ = sourceLen
	_ = runIt
	_ = cleanupNow
	_ = cleanupSource
	_ = enableDebugger
	panic("PicocParse not yet implemented in Go port")
}

func PicocParseInteractive(pc *Picoc) {
	_ = pc
	panic("PicocParseInteractive not yet implemented in Go port")
}

func PicocParseInteractiveNoStartPrompt(pc *Picoc, enableDebugger bool) {
	_ = pc
	_ = enableDebugger
	panic("PicocParseInteractiveNoStartPrompt not yet implemented in Go port")
}

func ParseStatement(parser *ParseState, checkTrailingSemicolon bool) ParseResult {
	_ = parser
	_ = checkTrailingSemicolon
	return ParseResultError
}

func ParseFunctionDefinition(parser *ParseState, returnType *ValueType, identifier string) *Value {
	_ = parser
	_ = returnType
	_ = identifier
	return nil
}

func ParseCleanup(pc *Picoc) {}

func ParserCopyPos(to *ParseState, from *ParseState) {
	*to = *from
}

func ParserCopy(to *ParseState, from *ParseState) {
	*to = *from
}
