// override these in your code to change the default behavior and style 
$.blockUI.defaults = { 
    // message displayed when blocking (use null for no message) 
    message:  '<img src="/images/loading.gif">', 
    css: { 
        zIndex: 2000,
	    position: 'fixed',
	    padding: '0px',
	    margin: '0px',
	    width: '30%',
	    top: '30%',
	    left: '35%',
	    textAlign: 'center',
	    backgroundColor : 'none',
	    border : 0,
	    cursor: 'wait'
    },
    // fadeIn time in millis; set to 0 to disable fadeIn on block 
    fadeIn:  200, 
 
    // fadeOut time in millis; set to 0 to disable fadeOut on unblock 
    fadeOut:  400,
    // style to replace wait cursor before unblocking to correct issue 
    // of lingering wait cursor 
    cursorReset: 'default', 
    // z-index for the blocking overlay 
	baseZ: 1000, 
    // disable if you don't want to show the overlay 
	showOverlay: true, 
    // styles for the overlay 
    overlayCSS:  { 
        backgroundColor: '#000', 
        opacity:         0.6, 
        cursor:          'wait' 
    }
};

$(document).ajaxStart($.blockUI).ajaxStop($.unblockUI);

$(function() {
    "use strict";
    /*
	 * ELEMENT EXIST OR NOT
	 * Description: returns true or false
	 * Usage: $('#myDiv').exists();
	 */
	$.fn.exists = function(){return this.length>0;}
	/*
	 * ELEMENT EXIST OR NOT
	 * Description: returns true or false
	 * Usage: $('#myDiv').hasAttr(AttrName);
	 */
	$.fn.hasAttr = function(name) {  
	   return this.attr(name) !== undefined;
	};
	/*
	 * ELEMENT EXIST OR NOT
	 * Description: returns true or false
	 * Usage: $('#myDiv').hasName(Name);
	 */
	$.fn.hasName = function(name) {
	    return this.name == name;
	};

	/* Project specific Javascript goes here. */
	$.fn.clearForm = function() {
	  return this.each(function() {
	    var type = this.type, tag = this.tagName.toLowerCase();
	    if (tag == 'form')
	      return $(':input',this).clearForm();
	    if (type == 'text' || type == 'password' || tag == 'textarea')
	      this.value = '';
	    else if (type == 'checkbox' || type == 'radio')
	      this.checked = false;
	    else if (tag == 'select')
	      this.selectedIndex = -1;
	  });
	};
});

function _Alert(type,message,title) {
	if(!title)
	{
		switch (type)
		{
			case "success":
			{
				title = 'Tuyệt vời!';
			}
			case "error":
			{
				title = 'Không ổn rồi!';
			}
			default:
			{
				title = 'Thông báo!';
			}
		}
	}

	return swal({
                  title: title,
                  type: type,
                  html:true,
                  text: message,
                  timer: 2000,
                  showConfirmButton: false
                });
}

function isEmpty(text) {
    if ((text === null) || (text === undefined) || (text === '')) return true;
    return false;
}

function addCommas(nStr)
{
    nStr += '';
    x = nStr.split('.');
    x1 = x[0];
    x2 = x.length > 1 ? '.' + x[1] : '';
    var rgx = /(\d+)(\d{3})/;
    while (rgx.test(x1)) {
        x1 = x1.replace(rgx, '$1' + ',' + '$2');
    }
    return x1 + x2;
}