package picoc

import (
	"fmt"
	"io"
	"math"
	"os"
	"strconv"
	"unsafe"
)

func BasicIOInit(pc *Picoc) {
	if pc != nil && pc.CStdOut == nil {
		pc.CStdOut = os.Stdout
	}
}

func LibraryInit(pc *Picoc) {
	if pc == nil {
		return
	}
	pc.VersionString = TableStrRegister(pc, "picoc-go")
	var bigEndian int
	var littleEndian int
	if isBigEndian() {
		bigEndian = 1
	} else {
		littleEndian = 1
	}
	VariableDefinePlatformVar(pc, nil, "PICOC_VERSION", pc.CharPtrType, (*AnyValue)(unsafe.Pointer(&pc.VersionString)), 0)
	VariableDefinePlatformVar(pc, nil, "BIG_ENDIAN", &pc.IntType, (*AnyValue)(unsafe.Pointer(&bigEndian)), 0)
	VariableDefinePlatformVar(pc, nil, "LITTLE_ENDIAN", &pc.IntType, (*AnyValue)(unsafe.Pointer(&littleEndian)), 0)
}

func LibraryAdd(pc *Picoc, funcList []LibraryFunction) {
	_ = pc
	for _, fn := range funcList {
		if fn.Prototype == "" {
			continue
		}
	}
}

func CLibraryInit(pc *Picoc) {
	BasicIOInit(pc)
	LibraryInit(pc)
	PlatformLibraryInit(pc)
}

func PrintCh(outCh byte, stream io.Writer) {
	if stream == nil {
		stream = os.Stdout
	}
	_, _ = stream.Write([]byte{outCh})
}

func PrintSimpleInt(num int64, stream io.Writer) {
	fmt.Fprint(stream, num)
}

func PrintInt(num int64, fieldWidth int, zeroPad int, leftJustify int, stream io.Writer) {
	_ = zeroPad
	_ = leftJustify
	if stream == nil {
		stream = os.Stdout
	}
	if fieldWidth > 0 {
		fmt.Fprintf(stream, "%*d", fieldWidth, num)
		return
	}
	fmt.Fprint(stream, num)
}

func PrintStr(str string, stream io.Writer) {
	if stream == nil {
		stream = os.Stdout
	}
	fmt.Fprint(stream, str)
}

func PrintFP(num float64, stream io.Writer) {
	if stream == nil {
		stream = os.Stdout
	}
	if math.IsInf(num, 0) || math.IsNaN(num) {
		fmt.Fprint(stream, num)
		return
	}
	fmt.Fprint(stream, strconv.FormatFloat(num, 'g', -1, 64))
}

func PrintType(typ *ValueType, stream io.Writer) {
	if stream == nil {
		stream = os.Stdout
	}
	if typ == nil {
		fmt.Fprint(stream, "<nil>")
		return
	}
	switch typ.Base {
	case TypeVoid:
		fmt.Fprint(stream, "void")
	case TypeInt:
		fmt.Fprint(stream, "int")
	case TypeShort:
		fmt.Fprint(stream, "short")
	case TypeChar:
		fmt.Fprint(stream, "char")
	case TypeLong:
		fmt.Fprint(stream, "long")
	case TypeUnsignedInt:
		fmt.Fprint(stream, "unsigned int")
	case TypeUnsignedShort:
		fmt.Fprint(stream, "unsigned short")
	case TypeUnsignedLong:
		fmt.Fprint(stream, "unsigned long")
	case TypeUnsignedChar:
		fmt.Fprint(stream, "unsigned char")
	case TypeFP:
		fmt.Fprint(stream, "double")
	case TypeFunction:
		fmt.Fprint(stream, "function")
	case TypeMacro:
		fmt.Fprint(stream, "macro")
	case TypePointer:
		if typ.FromType != nil {
			PrintType(typ.FromType, stream)
		}
		fmt.Fprint(stream, "*")
	case TypeArray:
		if typ.FromType != nil {
			PrintType(typ.FromType, stream)
		}
		fmt.Fprint(stream, "[")
		if typ.ArraySize != 0 {
			fmt.Fprint(stream, typ.ArraySize)
		}
		fmt.Fprint(stream, "]")
	case TypeStruct:
		fmt.Fprint(stream, "struct ")
		fmt.Fprint(stream, typ.Identifier)
	case TypeUnion:
		fmt.Fprint(stream, "union ")
		fmt.Fprint(stream, typ.Identifier)
	case TypeEnum:
		fmt.Fprint(stream, "enum ")
		fmt.Fprint(stream, typ.Identifier)
	case TypeGotoLabel:
		fmt.Fprint(stream, "goto label")
	case TypeType:
		fmt.Fprint(stream, "type")
	default:
		fmt.Fprint(stream, typ.Identifier)
	}
}

func LibPrintf(parser *ParseState, returnValue *Value, param []*Value, numArgs int) {
	_ = parser
	_ = returnValue
	_ = param
	_ = numArgs
}

func StdioSetupFunc(pc *Picoc) {}
func MathSetupFunc(pc *Picoc) {}
func StringSetupFunc(pc *Picoc) {}
func StdlibSetupFunc(pc *Picoc) {}
func StdTimeSetupFunc(pc *Picoc) {}
func StdErrnoSetupFunc(pc *Picoc) {}
func StdboolSetupFunc(pc *Picoc) {}
func UnistdSetupFunc(pc *Picoc) {}

var StdioDefs string
var StdTimeDefs string
var StdboolDefs string
var UnistdDefs string

var StdioFunctions = []LibraryFunction{}
var MathFunctions = []LibraryFunction{}
var StringFunctions = []LibraryFunction{}
var StdlibFunctions = []LibraryFunction{}
var StdTimeFunctions = []LibraryFunction{}
var StdCtypeFunctions = []LibraryFunction{}
var UnistdFunctions = []LibraryFunction{}

func isBigEndian() bool {
	var probe uint16 = 0x0102
	return *(*byte)(unsafe.Pointer(&probe)) == 0x01
}
