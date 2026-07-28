package picoc

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"sync"
	"unsafe"
)

const (
	GlobalTableSize        = 97
	StringTableSize        = 97
	StringLiteralTableSize = 97
	ReservedWordTableSize  = 97
	LocalTableSize         = 11
	StructTableSize        = 11
	ParameterMax           = 16
	LineBufferMax          = 256
	FreeListBuckets        = 8
	BreakPointTableSize    = 21
)

type RunMode int

const (
	RunModeRun RunMode = iota
	RunModeSkip
	RunModeReturn
	RunModeCaseSearch
	RunModeBreak
	RunModeContinue
	RunModeGoto
)

type BaseType int

const (
	TypeVoid BaseType = iota
	TypeInt
	TypeShort
	TypeChar
	TypeLong
	TypeUnsignedInt
	TypeUnsignedShort
	TypeUnsignedChar
	TypeUnsignedLong
	TypeFP
	TypeFunction
	TypeMacro
	TypePointer
	TypeArray
	TypeStruct
	TypeUnion
	TypeEnum
	TypeGotoLabel
	TypeType
)

type LexToken int

const (
	TokenNone LexToken = iota
	TokenComma
	TokenAssign
	TokenAddAssign
	TokenSubtractAssign
	TokenMultiplyAssign
	TokenDivideAssign
	TokenModulusAssign
	TokenShiftLeftAssign
	TokenShiftRightAssign
	TokenArithmeticAndAssign
	TokenArithmeticOrAssign
	TokenArithmeticExorAssign
	TokenQuestionMark
	TokenColon
	TokenLogicalOr
	TokenLogicalAnd
	TokenArithmeticOr
	TokenArithmeticExor
	TokenAmpersand
	TokenEqual
	TokenNotEqual
	TokenLessThan
	TokenGreaterThan
	TokenLessEqual
	TokenGreaterEqual
	TokenShiftLeft
	TokenShiftRight
	TokenPlus
	TokenMinus
	TokenAsterisk
	TokenSlash
	TokenModulus
	TokenIncrement
	TokenDecrement
	TokenUnaryNot
	TokenUnaryExor
	TokenSizeof
	TokenCast
	TokenLeftSquareBracket
	TokenRightSquareBracket
	TokenDot
	TokenArrow
	TokenOpenBracket
	TokenCloseBracket
	TokenIdentifier
	TokenIntegerConstant
	TokenFPConstant
	TokenStringConstant
	TokenCharacterConstant
	TokenSemicolon
	TokenEllipsis
	TokenLeftBrace
	TokenRightBrace
	TokenIntType
	TokenCharType
	TokenFloatType
	TokenDoubleType
	TokenVoidType
	TokenEnumType
	TokenLongType
	TokenSignedType
	TokenShortType
	TokenStaticType
	TokenAutoType
	TokenRegisterType
	TokenExternType
	TokenStructType
	TokenUnionType
	TokenUnsignedType
	TokenTypedef
	TokenContinue
	TokenDo
	TokenElse
	TokenFor
	TokenGoto
	TokenIf
	TokenWhile
	TokenBreak
	TokenSwitch
	TokenCase
	TokenDefault
	TokenReturn
	TokenHashDefine
	TokenHashInclude
	TokenHashIf
	TokenHashIfdef
	TokenHashIfndef
	TokenHashElse
	TokenHashEndif
	TokenNew
	TokenDelete
	TokenOpenMacroBracket
	TokenEOF
	TokenEndOfLine
	TokenEndOfFunction
	TokenBackSlash
)

type ValueType struct {
	Base            BaseType
	ArraySize       int
	Sizeof          int
	AlignBytes      int
	Identifier      string
	FromType        *ValueType
	DerivedTypeList *ValueType
	Next            *ValueType
	Members         *Table
	OnHeap          bool
	StaticQualifier int
}

type FuncDef struct {
	ReturnType *ValueType
	NumParams  int
	VarArgs    bool
	ParamType  []*ValueType
	ParamName  []string
	Intrinsic  func(*ParseState, *Value, []*Value, int)
	Body       ParseState
}

type MacroDef struct {
	NumParams int
	ParamName []string
	Body      ParseState
}

type AnyValue struct {
	Character           byte
	ShortInteger        int16
	Integer             int
	LongInteger         int64
	UnsignedShortInteger uint16
	UnsignedInteger     uint32
	UnsignedLongInteger  uint64
	UnsignedCharacter   byte
	Identifier         string
	ArrayMem           [2]byte
	Typ                *ValueType
	FuncDef            FuncDef
	MacroDef           MacroDef
	FP                 float64
	Pointer            unsafe.Pointer
}

type Value struct {
	Typ          *ValueType
	Val          *AnyValue
	LValueFrom   *Value
	ValOnHeap    bool
	ValOnStack   bool
	AnyValOnHeap bool
	IsLValue     bool
	ScopeID      int
	OutOfScope   bool
}

type TableEntry struct {
	Next         *TableEntry
	DeclFileName string
	DeclLine     int
	DeclColumn   int
	Key          string
	Val          *Value
}

type Table struct {
	Size      int
	OnHeap    bool
	HashTable map[string]*TableEntry
}

type StackFrame struct {
	ReturnParser       ParseState
	FuncName           string
	ReturnValue        *Value
	Parameter          []*Value
	NumParams          int
	LocalTable         Table
	LocalHashTable     [LocalTableSize]*TableEntry
	PreviousStackFrame  *StackFrame
}

type LexMode int

const (
	LexModeNormal LexMode = iota
	LexModeHashInclude
	LexModeHashDefine
	LexModeHashDefineSpace
	LexModeHashDefineSpaceIdent
)

type LexState struct {
	Pos              string
	End              string
	FileName         string
	Line             int
	CharacterPos     int
	SourceText       string
	Mode             LexMode
	EmitExtraNewlines int
}

type LibraryFunction struct {
	Func      func(*ParseState, *Value, []*Value, int)
	Prototype string
}

type OutputStreamInfo struct {
	Parser   *ParseState
	WritePos *strings.Builder
}

type OutputStream struct {
	Putch func(byte, *OutputStreamInfo)
	i     OutputStreamInfo
}

type ParseResult int

const (
	ParseResultEOF ParseResult = iota
	ParseResultError
	ParseResultOk
)

type CleanupTokenNode struct {
	Tokens     any
	SourceText string
	Next       *CleanupTokenNode
}

type TokenLine struct {
	Next     *TokenLine
	Tokens   []byte
	NumBytes int
}

type IncludeLibrary struct {
	IncludeName  string
	SetupFunction func(*Picoc)
	FuncList      []LibraryFunction
	SetupCSource  string
	NextLib       *IncludeLibrary
}

type ParseState struct {
	pc                    *Picoc
	Pos                   int
	FileName              string
	Line                  int
	CharacterPos          int
	Mode                  RunMode
	SearchLabel           int
	SearchGotoLabel       string
	SourceText            string
	HashIfLevel           int
	HashIfEvaluateToLevel int
	DebugMode             byte
	ScopeID               int
}

type AllocNode struct {
	Size     int
	NextFree *AllocNode
}

type Picoc struct {
	GlobalTable            Table
	CleanupTokenList       *CleanupTokenNode
	GlobalHashTable        [GlobalTableSize]*TableEntry
	InteractiveHead        *TokenLine
	InteractiveTail        *TokenLine
	InteractiveCurrentLine *TokenLine
	LexUseStatementPrompt  int
	LexAnyValue            AnyValue
	LexValue               Value
	ReservedWordTable      Table
	ReservedWordHashTable  [ReservedWordTableSize]*TableEntry
	StringLiteralTable     Table
	StringLiteralHashTable [StringLiteralTableSize]*TableEntry
	TopStackFrame          *StackFrame
	PicocExitValue         int
	IncludeLibList         *IncludeLibrary
	HeapMemory             []byte
	HeapBottom             int
	StackFramePtr          int
	HeapStackTop           int
	FreeListBucket         [FreeListBuckets]*AllocNode
	FreeListBig            *AllocNode
	UberType               ValueType
	IntType                ValueType
	ShortType              ValueType
	CharType               ValueType
	LongType               ValueType
	UnsignedIntType        ValueType
	UnsignedShortType      ValueType
	UnsignedLongType       ValueType
	UnsignedCharType       ValueType
	FPType                 ValueType
	VoidType               ValueType
	TypeType               ValueType
	FunctionType           ValueType
	MacroType              ValueType
	EnumType               ValueType
	GotoLabelType          ValueType
	CharPtrType            *ValueType
	CharPtrPtrType         *ValueType
	CharArrayType          *ValueType
	VoidPtrType            *ValueType
	BreakpointTable        Table
	BreakpointHashTable    [BreakPointTableSize]*TableEntry
	BreakpointCount        int
	DebugManualBreak       bool
	BigEndian              int
	LittleEndian           int
	CStdOut                io.Writer
	VersionString          string
	StringTable            Table
	StringHashTable        [StringTableSize]*TableEntry
	StrEmpty               string
	heapAllocations        map[uintptr][]byte
	heapAllocMu            sync.Mutex
}

func memAlign(size int) int {
	word := int(unsafe.Sizeof(uintptr(0)))
	if word <= 0 {
		return size
	}
	return (size + word - 1) & ^(word - 1)
}

func New() *Picoc {
	pc := &Picoc{CStdOut: os.Stdout, VersionString: "go-port", heapAllocations: make(map[uintptr][]byte)}
	PicocInitialize(pc, 128000*4)
	return pc
}

func PicocInitialize(pc *Picoc, stackSize int) {
	PlatformInit(pc)
	BasicIOInit(pc)
	HeapInit(pc, stackSize)
	TableInit(pc)
	VariableInit(pc)
	LexInit(pc)
	TypeInit(pc)
	IncludeInit(pc)
	LibraryInit(pc)
	PlatformLibraryInit(pc)
}

func PicocCleanup(pc *Picoc) {
	IncludeCleanup(pc)
	ParseCleanup(pc)
	LexCleanup(pc)
	VariableCleanup(pc)
	TypeCleanup(pc)
	TableStrFree(pc)
	HeapCleanup(pc)
	PlatformCleanup(pc)
}

func Main(args []string) int {
	pc := &Picoc{CStdOut: os.Stdout, VersionString: "go-port", heapAllocations: make(map[uintptr][]byte)}
	stackSize := 128000 * 4
	if raw := os.Getenv("STACKSIZE"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil {
			stackSize = parsed
		}
	}
	if len(args) < 1 || args[0] == "-h" {
		fmt.Fprintln(pc.CStdOut, "picoc go-port")
		fmt.Fprintln(pc.CStdOut, "Format:\n")
		fmt.Fprintln(pc.CStdOut, "> picoc <file1.c>... [- <arg1>...]    : run a program, calls main() as the entry point")
		fmt.Fprintln(pc.CStdOut, "> picoc -s <file1.c>... [- <arg1>...] : run a script, runs the program without calling main()")
		fmt.Fprintln(pc.CStdOut, "> picoc -i                            : interactive mode, Ctrl+d to exit")
		fmt.Fprintln(pc.CStdOut, "> picoc -c                            : copyright info")
		fmt.Fprintln(pc.CStdOut, "> picoc -h                            : this help message")
		return 0
	}
	if args[0] == "-c" {
		fmt.Fprintln(pc.CStdOut, "picoc go-port")
		return 0
	}
	PicocInitialize(pc, stackSize)
	defer PicocCleanup(pc)
	if args[0] == "-s" {
		PicocIncludeAllSystemHeaders(pc)
		args = args[1:]
	}
	if len(args) > 0 && args[0] == "-i" {
		PicocIncludeAllSystemHeaders(pc)
		PicocParseInteractive(pc)
		return pc.PicocExitValue
	}
	for _, arg := range args {
		if arg == "-" {
			break
		}
		PicocPlatformScanFile(pc, arg)
	}
	if idx := indexOf(args, "-"); idx >= 0 && idx < len(args)-1 {
		PicocCallMain(pc, len(args)-idx-1, args[idx+1:])
	}
	return pc.PicocExitValue
}

func indexOf(items []string, needle string) int {
	for i, item := range items {
		if item == needle {
			return i
		}
	}
	return -1
}

func TableInit(pc *Picoc) {
	TableInitTable(&pc.StringTable, pc.StringHashTable[:], StringTableSize, true)
	pc.StrEmpty = TableStrRegister(pc, "")
}

func TableInitTable(tbl *Table, hashTable []*TableEntry, size int, onHeap bool) {
	_ = hashTable
	tbl.Size = size
	tbl.OnHeap = onHeap
	tbl.HashTable = make(map[string]*TableEntry, size)
}

func TableSet(pc *Picoc, tbl *Table, key string, val *Value, declFileName string, declLine, declColumn int) bool {
	if tbl.HashTable == nil {
		tbl.HashTable = make(map[string]*TableEntry)
	}
	if _, exists := tbl.HashTable[key]; exists {
		return false
	}
	tbl.HashTable[key] = &TableEntry{DeclFileName: declFileName, DeclLine: declLine, DeclColumn: declColumn, Key: key, Val: val}
	return true
}

func TableGet(tbl *Table, key string) (*Value, string, int, int, bool) {
	if tbl == nil || tbl.HashTable == nil {
		return nil, "", 0, 0, false
	}
	entry, ok := tbl.HashTable[key]
	if !ok {
		return nil, "", 0, 0, false
	}
	return entry.Val, entry.DeclFileName, entry.DeclLine, entry.DeclColumn, true
}

func TableDelete(pc *Picoc, tbl *Table, key string) *Value {
	if tbl == nil || tbl.HashTable == nil {
		return nil
	}
	entry, ok := tbl.HashTable[key]
	if !ok {
		return nil
	}
	delete(tbl.HashTable, key)
	return entry.Val
}

func TableSetIdentifier(pc *Picoc, tbl *Table, ident string, identLen int) string {
	if identLen >= 0 && identLen < len(ident) {
		ident = ident[:identLen]
	}
	if tbl != nil {
		if tbl.HashTable == nil {
			tbl.HashTable = make(map[string]*TableEntry)
		}
		if _, exists := tbl.HashTable[ident]; !exists {
			tbl.HashTable[ident] = &TableEntry{Key: ident}
		}
	}
	return ident
}

func TableStrRegister2(pc *Picoc, str string, length int) string {
	return TableSetIdentifier(pc, &pc.StringTable, str, length)
}

func TableStrRegister(pc *Picoc, str string) string {
	return TableStrRegister2(pc, str, len(str))
}

func TableStrFree(pc *Picoc) {
	if pc != nil {
		pc.StringTable.HashTable = make(map[string]*TableEntry)
	}
}

func HeapInit(pc *Picoc, stackOrHeapSize int) {
	pc.HeapMemory = make([]byte, stackOrHeapSize)
	pc.HeapBottom = len(pc.HeapMemory)
	pc.StackFramePtr = 0
	pc.HeapStackTop = 0
	pc.FreeListBig = nil
	for i := range pc.FreeListBucket {
		pc.FreeListBucket[i] = nil
	}
}

func HeapCleanup(pc *Picoc) {
	pc.HeapMemory = nil
	pc.heapAllocMu.Lock()
	pc.heapAllocations = make(map[uintptr][]byte)
	pc.heapAllocMu.Unlock()
}

func HeapAllocStack(pc *Picoc, size int) unsafe.Pointer {
	aligned := memAlign(size)
	if pc.HeapStackTop+aligned > pc.HeapBottom {
		return nil
	}
	start := pc.HeapStackTop
	pc.HeapStackTop += aligned
	for i := 0; i < size; i++ {
		pc.HeapMemory[start+i] = 0
	}
	return unsafe.Pointer(&pc.HeapMemory[start])
}

func HeapUnpopStack(pc *Picoc, size int) {
	pc.HeapStackTop += memAlign(size)
}

func HeapPopStack(pc *Picoc, addr unsafe.Pointer, size int) bool {
	lose := memAlign(size)
	if lose > pc.HeapStackTop {
		return false
	}
	pc.HeapStackTop -= lose
	if addr != nil {
		if uintptr(addr) != uintptr(unsafe.Pointer(&pc.HeapMemory[pc.HeapStackTop])) {
			return false
		}
	}
	return true
}

func HeapPushStackFrame(pc *Picoc) {
	if pc.HeapStackTop+int(unsafe.Sizeof(uintptr(0))) > len(pc.HeapMemory) {
		return
	}
	pc.StackFramePtr = pc.HeapStackTop
	pc.HeapStackTop += int(unsafe.Sizeof(uintptr(0)))
}

func HeapPopStackFrame(pc *Picoc) bool {
	if pc.StackFramePtr == 0 {
		return false
	}
	pc.HeapStackTop = pc.StackFramePtr
	pc.StackFramePtr = 0
	return true
}

func HeapAllocMem(pc *Picoc, size int) unsafe.Pointer {
	if size <= 0 {
		size = 1
	}
	block := make([]byte, size)
	ptr := unsafe.Pointer(&block[0])
	pc.heapAllocMu.Lock()
	pc.heapAllocations[uintptr(ptr)] = block
	pc.heapAllocMu.Unlock()
	return ptr
}

func HeapFreeMem(pc *Picoc, mem unsafe.Pointer) {
	if pc == nil || mem == nil {
		return
	}
	pc.heapAllocMu.Lock()
	delete(pc.heapAllocations, uintptr(mem))
	pc.heapAllocMu.Unlock()
}

func PlatformInit(pc *Picoc) {
	pc.CStdOut = os.Stdout
}

func PlatformCleanup(pc *Picoc) {}

func PlatformReadFile(pc *Picoc, fileName string) (string, error) {
	data, err := os.ReadFile(fileName)
	if err != nil {
		return "", err
	}
	text := string(data)
	if strings.HasPrefix(text, "#!") {
		lineEnd := strings.IndexAny(text, "\r\n")
		if lineEnd < 0 {
			return strings.Repeat(" ", len(text)), nil
		}
		return strings.Repeat(" ", lineEnd) + text[lineEnd:], nil
	}
	return text, nil
}

func PicocPlatformScanFile(pc *Picoc, fileName string) {
	text, err := PlatformReadFile(pc, fileName)
	if err != nil {
		panic(err)
	}
	PicocParse(pc, fileName, text, len(text), true, false, true, false)
}

func PicocCallMain(pc *Picoc, argc int, argv []string) {
	panic("PicocCallMain not yet ported")
}

func VariableInit(pc *Picoc) {}

func VariableCleanup(pc *Picoc) {}

func TypeInit(pc *Picoc) {
	pc.UberType.DerivedTypeList = nil
	addBaseType(pc, &pc.IntType, TypeInt, int(unsafe.Sizeof(int(0))), 1)
	addBaseType(pc, &pc.ShortType, TypeShort, int(unsafe.Sizeof(int16(0))), 1)
	addBaseType(pc, &pc.CharType, TypeChar, int(unsafe.Sizeof(byte(0))), 1)
	addBaseType(pc, &pc.LongType, TypeLong, int(unsafe.Sizeof(int64(0))), 1)
	addBaseType(pc, &pc.UnsignedIntType, TypeUnsignedInt, int(unsafe.Sizeof(uint(0))), 1)
	addBaseType(pc, &pc.UnsignedShortType, TypeUnsignedShort, int(unsafe.Sizeof(uint16(0))), 1)
	addBaseType(pc, &pc.UnsignedLongType, TypeUnsignedLong, int(unsafe.Sizeof(uint64(0))), 1)
	addBaseType(pc, &pc.UnsignedCharType, TypeUnsignedChar, int(unsafe.Sizeof(byte(0))), 1)
	addBaseType(pc, &pc.VoidType, TypeVoid, 0, 1)
	addBaseType(pc, &pc.FunctionType, TypeFunction, int(unsafe.Sizeof(int(0))), 1)
	addBaseType(pc, &pc.MacroType, TypeMacro, int(unsafe.Sizeof(int(0))), 1)
	addBaseType(pc, &pc.GotoLabelType, TypeGotoLabel, 0, 1)
	addBaseType(pc, &pc.FPType, TypeFP, int(unsafe.Sizeof(float64(0))), 1)
	addBaseType(pc, &pc.TypeType, TypeType, int(unsafe.Sizeof(float64(0))), 1)
	pc.CharArrayType = typeAdd(pc, nil, &pc.CharType, TypeArray, 0, pc.StrEmpty, int(unsafe.Sizeof(byte(0))), 1)
	pc.CharPtrType = typeAdd(pc, nil, &pc.CharType, TypePointer, 0, pc.StrEmpty, int(unsafe.Sizeof(uintptr(0))), 1)
	pc.CharPtrPtrType = typeAdd(pc, nil, pc.CharPtrType, TypePointer, 0, pc.StrEmpty, int(unsafe.Sizeof(uintptr(0))), 1)
	pc.VoidPtrType = typeAdd(pc, nil, &pc.VoidType, TypePointer, 0, pc.StrEmpty, int(unsafe.Sizeof(uintptr(0))), 1)
}

func TypeCleanup(pc *Picoc) {}

func typeAdd(pc *Picoc, parser *ParseState, parentType *ValueType, base BaseType, arraySize int, identifier string, sizeof int, alignBytes int) *ValueType {
	_ = parser
	newType := &ValueType{Base: base, ArraySize: arraySize, Sizeof: sizeof, AlignBytes: alignBytes, Identifier: identifier, FromType: parentType, OnHeap: true}
	newType.Next = parentType.DerivedTypeList
	parentType.DerivedTypeList = newType
	return newType
}

func addBaseType(pc *Picoc, typeNode *ValueType, base BaseType, sizeof int, alignBytes int) {
	typeNode.Base = base
	typeNode.ArraySize = 0
	typeNode.Sizeof = sizeof
	typeNode.AlignBytes = alignBytes
	typeNode.Identifier = pc.StrEmpty
	typeNode.Members = nil
	typeNode.FromType = nil
	typeNode.DerivedTypeList = nil
	typeNode.OnHeap = false
	typeNode.Next = pc.UberType.DerivedTypeList
	pc.UberType.DerivedTypeList = typeNode
}

func TypeSizeValue(val *Value, compact bool) int {
	if val == nil || val.Typ == nil {
		return 0
	}
	if val.Typ.Base != TypeArray {
		return val.Typ.Sizeof
	}
	if val.Typ.FromType == nil {
		return 0
	}
	return val.Typ.FromType.Sizeof * val.Typ.ArraySize
}

func TypeSize(typ *ValueType, arraySize int, compact bool) int {
	if typ == nil {
		return 0
	}
	if typ.Base != TypeArray {
		return typ.Sizeof
	}
	if typ.FromType == nil {
		return 0
	}
	return typ.FromType.Sizeof * arraySize
}

func TypeStackSizeValue(val *Value) int {
	if val != nil && val.ValOnStack {
		return TypeSizeValue(val, false)
	}
	return 0
}

func PlatformGetLine(prompt string) (string, error) {
	if prompt != "" {
		fmt.Fprint(os.Stdout, prompt)
	}
	reader := bufio.NewReader(os.Stdin)
	line, err := reader.ReadString('\n')
	return line, err
}

func PlatformGetCharacter() (int, error) {
	reader := bufio.NewReader(os.Stdin)
	ch, _, err := reader.ReadRune()
	return int(ch), err
}

func PlatformPutc(outCh byte, stream *OutputStreamInfo) {
	if stream != nil && stream.WritePos != nil {
		_ = stream.WritePos.WriteByte(outCh)
		return
	}
	_, _ = os.Stdout.Write([]byte{outCh})
}

func PlatformExit(pc *Picoc, retVal int) {
	pc.PicocExitValue = retVal
	panic(fmt.Sprintf("picoc exit %d", retVal))
}

func PlatformLibraryInit(pc *Picoc) {}
