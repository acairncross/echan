function quote(p_id){
  textarea = document.getElementById('comment')
  curText = textarea.value
  if(textarea.selectionStart || "0" == textarea.selectionStart){
    var b = textarea.selectionEnd;
    textarea.value = curText.substring(0, textarea.selectionStart)
      + ">>"
      + p_id
      + "\n"
      + curText.substring(b, curText.length)
  } else {
    textarea.value += ">>" + a + "\n"
  }
}