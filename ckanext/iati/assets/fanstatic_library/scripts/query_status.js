$(document).ready(function() {
        function capitalizeFirstLetter(string) {
          return string.charAt(0).toUpperCase() + string.slice(1).toLowerCase();
      }

      function datasetLink(id) {
          return "<div><li><a href=\"/dataset/" + id + "/\">" + id + "</a></li></div>"
      }

      function notificationPrint(notification) {
          return "<div><li>" + notification + "</li></div>"
      }

      var PollState = function(task_id) {
          $.ajax({
              url: "/csv/check_status/" + "{{task_id}}",
              type: "GET",
          }).done(function(task) {
              task = JSON.parse(task)
              $("#result").html("<h4>Status: " + capitalizeFirstLetter(task.status) + "</h4>");
              if (task.status !== "SUCCESS") {
                  // $("#summary").css("display", "none");
                  $("#wait").css("display", "block");
                  setTimeout(PollState, 5000, task_id)
              } else if (task.status === 'SUCCESS') {
                  $("#wait").css("display", "none");
                  $("#summary").removeClass("hidden").addClass("shown");
                  $.each(task.result, function(key, value) {
                      if (key === "added" || key === "updated") {
                          $("#" + key + "-count").text(value.length)
                          if (value.length) {
                              $("#" + key + "-inner").empty()
                              $.each(value, function(index, res) {
                                  $("#" + key + "-inner").append(datasetLink(res))
                              })
                          }
                      } else if (key == "warnings" || key == "errors") {
                          $("#" + key + "-count").text(value.length)
                          $.each(value, function(row, fields) {
                              $("#" + key + "-inner").empty()
                              $("#" + key + "-inner").append(notificationPrint(fields[1]['file']))
                          })
                      }
                  });

              }
          });
      }
      PollState("{{task_id}}")
      });