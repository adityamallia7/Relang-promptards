package picoc

func ExpressionParse(parser *ParseState, result **Value) int {
	_ = parser
	_ = result
	return 0
}

func ExpressionParseInt(parser *ParseState) int64 {
	_ = parser
	return 0
}

func ExpressionAssign(parser *ParseState, destValue *Value, sourceValue *Value, force int, funcName string, paramNo int, allowPointerCoercion int) {
	_ = parser
	_ = destValue
	_ = sourceValue
	_ = force
	_ = funcName
	_ = paramNo
	_ = allowPointerCoercion
}

func ExpressionCoerceInteger(val *Value) int64 { return 0 }
func ExpressionCoerceUnsignedInteger(val *Value) uint64 { return 0 }
func ExpressionCoerceFP(val *Value) float64 { return 0 }
